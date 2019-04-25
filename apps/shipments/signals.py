import logging

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.conf import settings
from django.contrib.gis.geos import Point
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from fieldsignals import post_save_changed

from apps.eth.models import TransactionReceipt
from apps.eth.signals import event_update
from apps.iot_client import AWSIoTError
from apps.jobs.models import JobState, MessageType, AsyncJob, AsyncActionType
from apps.jobs.signals import job_update
from .events import LoadEventHandler
from .iot_client import DeviceAWSIoTClient
from .models import Shipment, LoadShipment, Location, TrackingData
from .rpc import RPCClientFactory
from .serializers import ShipmentVaultSerializer

LOG = logging.getLogger('transmission')

channel_layer = get_channel_layer()  # pylint:disable=invalid-name


@receiver(job_update, sender=Shipment, dispatch_uid='shipment_job_update')
def shipment_job_update(sender, message, listener, **kwargs):
    LOG.debug(f'Shipment job update with message {message.id}.')

    if message.type == MessageType.ETH_TRANSACTION:
        LOG.debug(f'Message type is {message.type}.')
        lookup_id = message.body['ethTxHash'] if 'ethTxHash' in message.body else message.body['transactionHash']
        TransactionReceipt.objects.filter(eth_action_id=lookup_id
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

        LOG.debug(f'Adding initial data for shipment: {instance.id}, to vault.')
        rpc_client.add_shipment_data(instance.storage_credentials_id, instance.shipper_wallet_id,
                                     instance.vault_id, ShipmentVaultSerializer(instance).data)

        # Create LoadShipment entities
        # TODO: Get FundingType,ShipmentAmount for use in LOAD Contract/LoadShipment
        LoadShipment.objects.create(shipment=instance,
                                    funding_type=Shipment.FUNDING_TYPE,
                                    contracted_amount=Shipment.SHIPMENT_AMOUNT)

        instance.vault_id = vault_id
        instance.vault_uri = vault_uri
        instance.save()
        # Save related history instance without user
        history_instance = instance.history.all().first()
        history_instance.history_user = None
        history_instance.save()

        shipment_device_id_changed(Shipment, instance, {Shipment.device.field: (None, instance.device_id)})
    else:
        # Update Shipment vault data
        rpc_client = RPCClientFactory.get_client()
        signature = rpc_client.add_shipment_data(instance.storage_credentials_id, instance.shipper_wallet_id,
                                                 instance.vault_id, ShipmentVaultSerializer(instance).data)
        LOG.debug(f'Updating LOAD contract with vault uri/hash {signature["hash"]}.')
        # Update LOAD contract with vault uri/hash
        instance.set_vault_hash(signature['hash'], action_type=AsyncActionType.SHIPMENT)


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


@receiver(pre_save, sender=TrackingData, dispatch_uid='trackingdata_pre_save')
def trackingdata_pre_save(sender, **kwargs):
    instance = kwargs["instance"]
    instance.point = Point(instance.longitude, instance.latitude)


@receiver(post_save, sender=TrackingData, dispatch_uid='trackingdata_post_save')
def trackingdata_post_save(sender, **kwargs):
    instance = kwargs["instance"]
    LOG.debug(f'New tracking_data committed to db and will be pushed to the UI. Tracking_data: {instance.id}.')
    async_to_sync(channel_layer.group_send)(instance.shipment.owner_id,
                                            {"type": "tracking_data.save", "tracking_data_id": instance.id})


@receiver(post_save_changed, sender=Shipment, fields=['delivery_act'], dispatch_uid='shipment_delivery_act_post_save')
def shipment_delivery_act_changed(sender, instance, changed_fields, **kwargs):
    logging.info(f'Shipment with id {instance.id} ended on {instance.delivery_act}.')

    device_id = instance.device_id
    Shipment.objects.filter(id=instance.id).update(device_id=None)
    shipment_device_id_changed(Shipment, instance, {Shipment.device.field: (device_id, None)})


@receiver(post_save_changed, sender=Shipment, fields=['device'], dispatch_uid='shipment_device_id_post_save')
def shipment_device_id_changed(sender, instance, changed_fields, **kwargs):
    if settings.IOT_THING_INTEGRATION:
        old, new = changed_fields[Shipment.device.field]

        logging.info(f'Device ID changed from {old} to {new} for Shipment {instance.id}, updating shadow')

        try:
            iot_client = DeviceAWSIoTClient()
            if old:
                iot_client.update_shadow(old, {'deviceId': old, 'shipmentId': ''})
            if new:
                iot_client.update_shadow(new, {'deviceId': new, 'shipmentId': instance.id})
        except AWSIoTError as exc:
            logging.error(f'Error communicating with AWS IoT during Device shadow shipmentId update: {exc}')
