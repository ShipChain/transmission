import logging

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.contrib.gis.geos import Point
from django.db.models.signals import pre_save, post_save
from django.dispatch import receiver
from django.urls import reverse
from fancy_cache.memory import find_urls

from apps.routes.models import RouteTrackingData

LOG = logging.getLogger('transmission')

channel_layer = get_channel_layer()  # pylint:disable=invalid-name


@receiver(pre_save, sender=RouteTrackingData, dispatch_uid='routetrackingdata_pre_save')
def routetrackingdata_pre_save(sender, **kwargs):
    instance = kwargs["instance"]
    instance.point = Point(instance.longitude, instance.latitude)


@receiver(post_save, sender=RouteTrackingData, dispatch_uid='routetrackingdata_post_save')
def routetrackingdata_post_save(sender, **kwargs):
    instance = kwargs["instance"]
    LOG.debug(f'New tracking_data committed to db and will be pushed to the UI. Tracking_data: {instance.id}.')

    # Invalidate cached tracking data view for each shipment in Route
    for leg in instance.route.routeleg_set.all():
        tracking_get_url = reverse('shipment-tracking', kwargs={'version': 'v1', 'pk': leg.shipment.id})
        list(find_urls([tracking_get_url + "*"], purge=True))

        # Notify websocket channel
        async_to_sync(channel_layer.group_send)(leg.shipment.owner_id,
                                                {"type": "tracking_data.save", "tracking_data_id": instance.id})