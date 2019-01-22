import datetime
import logging

from django.contrib.gis.serializers.geojson import Serializer as GeoSerializer
from influxdb_metrics.loader import log_metric

LOG = logging.getLogger('transmission')


def render_point_features(shipment, tracking_data):
    """
    :param shipment: Shipment to be used for datetime filtering
    :param tracking_data: queryset of TrackingData objects
    :return: All tracking coordinates each in their own GeoJSON Point Feature
    """
    log_metric('transmission.info', tags={'method': 'build_point_features', 'module': __name__})
    LOG.debug(f'Build point features for shipment: {shipment.id}.')

    begin = (shipment.pickup_act or datetime.datetime.min).replace(tzinfo=datetime.timezone.utc)
    end = (shipment.delivery_act or datetime.datetime.max).replace(tzinfo=datetime.timezone.utc)

    tracking_data = tracking_data.filter(timestamp__range=(begin, end))

    geojson_data_as_point = GeoSerializer().serialize(
        tracking_data,
        geometry_field='point',
        fields=('uncertainty', 'source', 'timestamp')
    )

    return geojson_data_as_point
