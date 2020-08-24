import logging

import requests
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.conf import settings
from django.contrib.gis.geos import Point
from django.core.cache import cache
from django.db.models.signals import post_save, pre_save, post_delete
from django.dispatch import receiver
from fancy_cache.memory import find_urls
from fieldsignals import post_save_changed
from rest_framework.exceptions import ValidationError
from rest_framework.reverse import reverse
from shipchain_common.exceptions import AWSIoTError

from apps.eth.models import TransactionReceipt
from apps.eth.signals import event_update
from apps.jobs.models import JobState, MessageType, AsyncJob, AsyncActionType
from apps.jobs.signals import job_update
from apps.sns import SNSClient
from .events import LoadEventHandler
from .iot_client import DeviceAWSIoTClient
from .models import Shipment, LoadShipment, Location, TrackingData, TransitState, TelemetryData, AccessRequest
from .rpc import RPCClientFactory
from .serializers import ShipmentVaultSerializer

LOG = logging.getLogger('transmission')

channel_layer = get_channel_layer()  # pylint:disable=invalid-name


@receiver(job_update, sender=Shipment, dispatch_uid='shipment_job_update')
def shipment_job_update(sender, message, shipment, **kwargs):
    LOG.debug(f'Shipment job update with message {message.id}.')

    if message.type == MessageType.ETH_TRANSACTION:
        LOG.debug(f'Message type is {message.type}.')
        lookup_id = message.body['transactionHash'] if 'transactionHash' in message.body else message.body['hash']
        TransactionReceipt.objects.filter(eth_action_id=lookup_id
                                          ).update(**TransactionReceipt.convert_receipt(message.body))
        message.async_job.state = JobState.COMPLETE
        message.async_job.save()


@receiver(event_update, sender=Shipment, dispatch_uid='shipment_event_update')
def shipment_event_update(sender, event, shipment, **kwargs):
    LOG.debug(f'Shipment event update ({event.event_name}) with listener {shipment.id}.')
    LoadEventHandler.handle(event, shipment)


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

        instance.anonymous_historical_change(vault_id=vault_id, vault_uri=vault_uri)

        shipment_afts_tracking_changed(Shipment, instance, {
            Shipment._meta.get_field('afts_tracking'): (None, instance.afts_tracking)
        })

        shipment_iot_fields_changed(Shipment, instance, {
            Shipment.device.field: (None, instance.device_id),
            Shipment.state.field: (None, instance.state)
        })
    else:
        # Update Shipment vault data
        rpc_client = RPCClientFactory.get_client()
        signature = rpc_client.add_shipment_data(instance.storage_credentials_id, instance.shipper_wallet_id,
                                                 instance.vault_id, ShipmentVaultSerializer(instance).data)
        LOG.debug(f'Updating LOAD contract with vault uri/hash {signature["hash"]}.')
        # Update LOAD contract with vault uri/hash
        instance.set_vault_hash(signature['hash'], action_type=AsyncActionType.SHIPMENT)

        async_to_sync(channel_layer.group_send)(instance.owner_id, {
            "type": "shipments.update",
            "shipment_id": instance.id
        })

    # Publish SNS message on any Shipment create/update
    if settings.SNS_CLIENT:
        SNSClient().shipment_update(instance)


@receiver(post_save, sender=LoadShipment, dispatch_uid='loadshipment_post_save')
def loadshipment_post_save(sender, **kwargs):
    instance, created = kwargs["instance"], kwargs["created"]
    LOG.debug(f'LoadShipment post save for Shipment: {instance.shipment.id}')
    if created:
        LOG.debug('Creating a shipment on the load contract.')
        # Create shipment on the LOAD contract
        AsyncJob.rpc_job_for_listener(
            rpc_method=RPCClientFactory.get_client().create_shipment_transaction,
            rpc_parameters=[instance.shipment.shipper_wallet_id,
                            instance.shipment.id],
            signing_wallet_id=instance.shipment.shipper_wallet_id,
            shipment=instance.shipment
        )


@receiver(pre_save, sender=Location, dispatch_uid='location_pre_save')
def location_pre_save(sender, **kwargs):
    instance = kwargs["instance"]
    # Get point info
    instance.get_lat_long_from_address()


@receiver(post_save, sender=AccessRequest, dispatch_uid='accessrequest_post_save')
@receiver(post_delete, sender=AccessRequest, dispatch_uid='accessrequest_post_delete')
def accessrequest_post_save(sender, **kwargs):
    instance = kwargs["instance"]
    # Clear cached accessrequests for user
    cache.delete(f'access_request_shipments_{instance.requester_id}')

    # Invalidate cached tracking data view to force permissions check
    tracking_get_url = reverse('shipment-tracking', kwargs={'version': 'v1', 'pk': instance.shipment.id})
    list(find_urls([tracking_get_url + "*"], purge=True))


@receiver(pre_save, sender=TrackingData, dispatch_uid='trackingdata_pre_save')
def trackingdata_pre_save(sender, **kwargs):
    instance = kwargs["instance"]
    instance.point = Point(instance.longitude, instance.latitude)


@receiver(post_save, sender=TrackingData, dispatch_uid='trackingdata_post_save')
def trackingdata_post_save(sender, **kwargs):
    instance = kwargs["instance"]
    LOG.debug(f'New tracking_data committed to db and will be pushed to the UI. Tracking_data: {instance.id}.')

    # Invalidate cached tracking data view
    tracking_get_url = reverse('shipment-tracking', kwargs={'version': 'v1', 'pk': instance.shipment.id})
    list(find_urls([tracking_get_url + "*"], purge=True))

    # Notify websocket channel
    async_to_sync(channel_layer.group_send)(instance.shipment.owner_id,
                                            {"type": "tracking_data.save", "tracking_data_id": instance.id})


@receiver(post_save, sender=TelemetryData, dispatch_uid='telemetrydata_post_save')
def telemetrydata_post_save(sender, **kwargs):
    instance = kwargs["instance"]
    LOG.debug(f'New telemetry_data committed to db and will be pushed to the UI. Telemetry_data: {instance.id}.')

    # Invalidate cached telemetry data view
    telemetry_get_url = reverse('shipment-telemetry-list',
                                kwargs={'version': 'v1', 'shipment_pk': instance.shipment.id})
    list(find_urls([telemetry_get_url + "*"], purge=True))

    # Notify websocket channel
    async_to_sync(channel_layer.group_send)(instance.shipment.owner_id,
                                            {"type": "telemetry_data.save", "telemetry_data_id": instance.id})


@receiver(post_save_changed, sender=Shipment, fields=['afts_tracking'], dispatch_uid='shipment_afts_tracking_changed')
def shipment_afts_tracking_changed(sender, instance, changed_fields, **kwargs):
    if instance.afts_tracking and settings.SNS_CLIENT:
        response = requests.post(f'{settings.AFTERSHIP_URL}trackings',
                                 json={'tracking': {'tracking_number': instance.afts_tracking}},
                                 headers={'aftership-api-key': settings.AFTERSHIP_API_KEY})
        if not response.ok:
            raise ValidationError('Supplied tracking number has already been imported')

        tracking_data = response.json()['data']['tracking']

        instance.anonymous_historical_change(shippers_reference=f'Quickadd Shipment: {instance.afts_tracking}',
                                             carrier_abbv=tracking_data['slug'])
        instance.refresh_from_db(fields=['shippers_reference', 'carrier_abbv'])

        SNSClient().aftership_tracking_update(instance, tracking_data['id'])


@receiver(post_save_changed, sender=Shipment, fields=['device', 'state', 'geofences'],
          dispatch_uid='shipment_iot_fields_post_save')
def shipment_iot_fields_changed(sender, instance, changed_fields, **kwargs):
    if settings.IOT_THING_INTEGRATION:
        iot_client = DeviceAWSIoTClient()

        shadow_update = {}
        device_field = Shipment._meta.get_field('device')
        if device_field in changed_fields:
            old, new = changed_fields[device_field]
            logging.info(f'Device ID changed from {old} to {new} for Shipment {instance.id}, updating shadow')
            if old:
                iot_client.update_shadow(old, {'deviceId': old, 'shipmentId': '', 'shipmentState': '', 'geofences': ''})
            if new:
                shadow_update['deviceId'] = new
                shadow_update['shipmentId'] = instance.id
                shadow_update['shipmentState'] = TransitState(instance.state).name
                shadow_update['geofences'] = instance.geofences

        state_field = Shipment._meta.get_field('state')
        if state_field in changed_fields:
            old, new = changed_fields[state_field]
            logging.info(f'Shipment state changed from {old} to {new} for Shipment {instance.id}, updating shadow')
            shadow_update['shipmentState'] = TransitState(instance.state).name

        geofences_field = Shipment._meta.get_field('geofences')
        if geofences_field in changed_fields:
            old, new = changed_fields[geofences_field]
            logging.info(f'Shipment geofences changed from {old} to {new} for Shipment {instance.id}, updating shadow')
            shadow_update['geofences'] = instance.geofences if instance.geofences else ''

        if instance.device_id:
            try:
                iot_client.update_shadow(instance.device_id, shadow_update)
            except AWSIoTError as exc:
                logging.error(f'Error communicating with AWS IoT during Device shadow update: {exc}')
