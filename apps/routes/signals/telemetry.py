import logging

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db.models.signals import post_save
from django.dispatch import receiver
from fancy_cache.memory import find_urls
from rest_framework.reverse import reverse

from apps.routes.models import RouteTelemetryData

LOG = logging.getLogger('transmission')

channel_layer = get_channel_layer()  # pylint:disable=invalid-name


@receiver(post_save, sender=RouteTelemetryData, dispatch_uid='routetelemetrydata_post_save')
def telemetrydata_post_save(sender, **kwargs):
    instance = kwargs["instance"]
    LOG.debug(f'New telemetry_data committed to db and will be pushed to the UI. Telemetry_data: {instance.id}.')

    # Invalidate cached telemetry data view for each shipment in Route
    for leg in instance.route.routeleg_set.all():
        telemetry_get_url = reverse('shipment-telemetry-list',
                                    kwargs={'version': 'v1', 'shipment_pk': leg.shipment.id})
        list(find_urls([telemetry_get_url + "*"], purge=True))

        # Notify websocket channel
        async_to_sync(channel_layer.group_send)(leg.shipment.owner_id,
                                                {"type": "telemetry_data.save", "telemetry_data_id": instance.id})
