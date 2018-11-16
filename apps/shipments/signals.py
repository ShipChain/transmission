import logging

from django.dispatch import receiver
from django.db.models.signals import post_save, pre_save

from apps.eth.signals import event_update
from apps.eth.models import TransactionReceipt
from apps.jobs.models import JobState, MessageType, AsyncJob
from apps.jobs.signals import job_update
from .models import Shipment, LoadShipmentTxm, LoadShipmentEth, Location, EscrowState, ShipmentState
from .rpc import RPCClientFactory
from .serializers import ShipmentVaultSerializer


LOG = logging.getLogger('transmission')


@receiver(job_update, sender=Shipment, dispatch_uid='shipment_job_update')
def shipment_job_update(sender, message, listener, **kwargs):
    LOG.debug(f'Shipment job update with message {message.id}.')

    if message.type == MessageType.ETH_TRANSACTION:
        LOG.debug(f'Message type is {message.type}.')
        TransactionReceipt.objects.filter(eth_action_id=message.body['transactionHash']
                                          ).update(**TransactionReceipt.convert_receipt(message.body))

        message.async_job.state = JobState.COMPLETE
        message.async_job.save()


@receiver(event_update, sender=Shipment, dispatch_uid='shipment_event_update')
def shipment_event_update(sender, event, listener, **kwargs):
    LOG.debug(f'Shipment event update with listener {listener.id}.')

    if event.event_name == "ShipmentCreated":
        LOG.debug(f'Handling ShipmentCreated Event.')
        listener.loaddataeth.shipper = event.return_values['msgSender']
        listener.loaddataeth.shipment_state = ShipmentState.CREATED
        listener.loaddataeth.save()

        # Add vault data to new Shipment
        rpc_client = RPCClientFactory.get_client()
        signature = rpc_client.add_shipment_data(listener.storage_credentials_id, listener.shipper_wallet_id,
                                                 listener.vault_id, ShipmentVaultSerializer(listener).data)

        # Update LOAD contract with vault uri/hash
        LOG.debug(f'Updating load contract with hash {signature["hash"]}.')
        listener.update_vault_hash(signature['hash'])

    elif event.event_name == "EscrowCreated":
        LOG.debug(f'Handling EscrowCreated Event.')
        listener.loaddataeth.funding_type = event.return_values['fundingType']
        listener.loaddataeth.contracted_amount = event.return_values['contractedAmount']
        listener.loaddataeth.created_at = event.return_values['createdAt']
        listener.loaddataeth.refund_address = event.return_values['msgSender']
        listener.loaddataeth.shipment_state = EscrowState.CREATED
        listener.loaddataeth.save()


@receiver(post_save, sender=Shipment, dispatch_uid='shipment_post_save')
def shipment_post_save(sender, **kwargs):
    instance, created = kwargs["instance"], kwargs["created"]
    LOG.debug(f'Shipment post save with shipment {instance.id}.')

    if created:
        # Create vault
        rpc_client = RPCClientFactory.get_client()
        vault_id = rpc_client.create_vault(instance.storage_credentials_id, instance.shipper_wallet_id,
                                           instance.carrier_wallet_id)

        LOG.debug(f'Created vault with vault_id {instance.vault_id}.')

        # Create LoadShipment entities
        # TODO: Get FundingType,ShipmentAmount for use in LOAD Contract/LoadShipment
        LoadShipmentTxm.objects.create(shipment=instance,
                                       funding_type=Shipment.FUNDING_TYPE,
                                       contracted_amount=Shipment.SHIPMENT_AMOUNT)

        LoadShipmentEth.objects.create(shipment=instance)

        instance.vault_id = vault_id
        Shipment.objects.filter(id=instance.id).update(vault_id=vault_id)
    else:
        # Update Shipment vault data
        rpc_client = RPCClientFactory.get_client()
        signature = rpc_client.add_shipment_data(instance.storage_credentials_id, instance.shipper_wallet_id,
                                                 instance.vault_id, ShipmentVaultSerializer(instance).data)
        LOG.debug(f'Updating LOAD contract with vault uri/hash {signature["hash"]}.')
        # Update LOAD contract with vault uri/hash
        instance.update_vault_hash(signature['hash'])


@receiver(post_save, sender=LoadShipmentTxm, dispatch_uid='loadshipmenttxm_post_save')
def loadshipmenttxm_post_save(sender, **kwargs):
    instance, created = kwargs["instance"], kwargs["created"]
    LOG.debug(f'LoadShipmentTxm post save for Shipment: {instance.shipment.id}')
    if created:
        LOG.debug(f'Creating a shipment on the load contract.')
        # Create shipment on the LOAD contract
        AsyncJob.rpc_job_for_listener(
            rpc_method=RPCClientFactory.get_client().create_shipment_transaction,
            rpc_parameters=[instance.shipment.shipper_wallet_id,
                            instance.shipment.id,
                            instance.funding_type.value,
                            instance.contracted_amount],
            signing_wallet_id=instance.shipment.shipper_wallet_id,
            listener=instance.shipment
        )
    else:
        # TODO: Update loadshipmenteth with new values
        pass


@receiver(pre_save, sender=Location, dispatch_uid='location_pre_save')
def location_pre_save(sender, **kwargs):
    instance = kwargs["instance"]
    # Get point info
    instance.get_lat_long_from_address()
