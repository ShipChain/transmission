import logging

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from django.dispatch import receiver
from django.db.models.signals import post_save, pre_save

from apps.eth.signals import event_update
from apps.eth.models import TransactionReceipt
from apps.jobs.models import JobState, MessageType, AsyncJob
from apps.jobs.signals import job_update
from .events import LoadEventHandler
from .models import Shipment, LoadShipment, Location, TrackingData
from .rpc import RPCClientFactory
from .serializers import ShipmentVaultSerializer


LOG = logging.getLogger('transmission')

# pylint:disable=invalid-name
# trackingdata_update = Signal(providing_args=["message"])
channel_layer = get_channel_layer()


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
    LOG.debug(f'Shipment event update ({event.event_name}) with listener {listener.id}.')
    LoadEventHandler.handle(event, listener)


@receiver(post_save, sender=Shipment, dispatch_uid='shipment_post_save')
def shipment_post_save(sender, **kwargs):
    instance, created = kwargs["instance"], kwargs["created"]
    LOG.debug(f'Shipment post save with shipment {instance.id}.')

    if created:
        # Create vault
        rpc_client = RPCClientFactory.get_client()
        vault_id, vault_uri = rpc_client.create_vault(instance.storage_credentials_id, instance.shipper_wallet_id,
                                                      instance.carrier_wallet_id)
        instance.vault_id = vault_id
        LOG.debug(f'Created vault with vault_id {instance.vault_id}.')

        # Create LoadShipment entities
        # TODO: Get FundingType,ShipmentAmount for use in LOAD Contract/LoadShipment
        LoadShipment.objects.create(shipment=instance,
                                    funding_type=Shipment.FUNDING_TYPE,
                                    contracted_amount=Shipment.SHIPMENT_AMOUNT)

        Shipment.objects.filter(id=instance.id).update(vault_id=vault_id, vault_uri=vault_uri)
    else:
        # Update Shipment vault data
        rpc_client = RPCClientFactory.get_client()
        signature = rpc_client.add_shipment_data(instance.storage_credentials_id, instance.shipper_wallet_id,
                                                 instance.vault_id, ShipmentVaultSerializer(instance).data)
        LOG.debug(f'Updating LOAD contract with vault uri/hash {signature["hash"]}.')
        # Update LOAD contract with vault uri/hash
        instance.set_vault_hash(signature['hash'])


@receiver(post_save, sender=LoadShipment, dispatch_uid='loadshipment_post_save')
def loadshipment_post_save(sender, **kwargs):
    instance, created = kwargs["instance"], kwargs["created"]
    LOG.debug(f'LoadShipment post save for Shipment: {instance.shipment.id}')
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


@receiver(pre_save, sender=Location, dispatch_uid='location_pre_save')
def location_pre_save(sender, **kwargs):
    instance = kwargs["instance"]
    # Get point info
    instance.get_lat_long_from_address()


@receiver(post_save, sender=TrackingData, dispatch_uid='trackingdata_post_save')
def trackingdata_post_save(sender, **kwargs):
    instance = kwargs["instance"]
    # New tracking data will be pushed to the UI
    LOG.debug(f'New tracking_data committed to db and will be pushed to the UI. Tracking_data: {instance.id}.')
    async_to_sync(channel_layer.group_send)(instance.shipment.owner_id,
                                            {"type": "tracking_data.save", "tracking_data_id": instance.id})
