import logging

from django.dispatch import receiver
from django.db.models.signals import post_save
from influxdb_metrics.loader import log_metric

from apps.eth.signals import event_update
from apps.eth.models import TransactionReceipt
from apps.jobs.models import JobState, MessageType, AsyncJob
from apps.jobs.signals import job_update
from .models import Shipment, LoadShipment
from .rpc import ShipmentRPCClient
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

    if event.event_name == "CreateNewShipmentEvent":
        LOG.debug(f'Event.event_name is CreateNewShipmentEvent.')
        listener.load_data.shipment_id = event.return_values['shipmentID']
        listener.load_data.start_block = event.block_number
        listener.load_data.shipment_created = True
        listener.load_data.save()

        # Add vault data to new Shipment
        rpc_client = ShipmentRPCClient()
        signature = rpc_client.add_shipment_data(listener.storage_credentials_id, listener.shipper_wallet_id,
                                                 listener.vault_id, ShipmentVaultSerializer(listener).data)

        # Update LOAD contract with vault uri/hash
        LOG.debug(f'Updating load contract with hash {signature["hash"]}.')
        listener.update_vault_hash(signature['hash'])


@receiver(post_save, sender=Shipment, dispatch_uid='shipment_post_save')
def shipment_post_save(sender, **kwargs):
    instance, created = kwargs["instance"], kwargs["created"]
    LOG.debug(f'Shipment post save with shipment {instance.id}.')

    if created:
        # Create vault
        rpc_client = ShipmentRPCClient()
        instance.vault_id = rpc_client.create_vault(instance.storage_credentials_id, instance.shipper_wallet_id,
                                                    instance.carrier_wallet_id)
        instance.save()
        LOG.debug(f'Creating vault with vault_id {instance.vault_id}.')

        # Create LoadShipment entity
        # TODO: Get FundingType,ShipmentAmount,ValidUntil for use in LOAD Contract/LoadShipment
        instance.load_data = LoadShipment.objects.create(shipment=instance,
                                                         shipper=instance.shipper_wallet_id,
                                                         carrier=instance.carrier_wallet_id,
                                                         valid_until=Shipment.VALID_UNTIL,
                                                         funding_type=Shipment.FUNDING_TYPE,
                                                         shipment_amount=Shipment.SHIPMENT_AMOUNT)
        instance.save()
    else:
        # Update Shipment vault data
        rpc_client = ShipmentRPCClient()
        signature = rpc_client.add_shipment_data(instance.storage_credentials_id, instance.shipper_wallet_id,
                                                 instance.vault_id, ShipmentVaultSerializer(instance).data)

        LOG.debug(f'Updating LOAD contract with vault uri/hash {signature["hash"]}.')
        # Update LOAD contract with vault uri/hash
        instance.update_vault_hash(signature['hash'])


@receiver(post_save, sender=LoadShipment, dispatch_uid='loadshipment_post_save')
def loadshipment_post_save(sender, **kwargs):
    instance, created = kwargs["instance"], kwargs["created"]
    LOG.debug(f'LoadShipment post save with sender {sender}.')
    if created:
        LOG.debug(f'Creating a shipment on the load contract.')
        # Create shipment on the LOAD contract
        AsyncJob.rpc_job_for_listener(
            rpc_class=ShipmentRPCClient,
            rpc_method=ShipmentRPCClient.create_shipment_transaction,
            rpc_parameters=[instance.shipment.shipper_wallet_id,
                            instance.shipment.carrier_wallet_id,
                            instance.valid_until,
                            instance.funding_type.value,
                            instance.shipment_amount],
            signing_wallet_id=instance.shipment.shipper_wallet_id,
            listener=instance.shipment
        )
