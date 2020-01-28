import datetime
import logging

from django.core.serializers.base import SerializationError
from django.contrib.gis.serializers.geojson import Serializer as GeoSerializer
from influxdb_metrics.loader import log_metric
from apps.utils import AliasSerializerMixin

LOG = logging.getLogger('transmission')


class TrackingDataSerializer(AliasSerializerMixin, GeoSerializer):
    pass


class BaseFeatureTrackingDataSerializer(TrackingDataSerializer):
    def start_serialization(self):
        self._init_options()
        self._cts = {}  # pylint:disable=attribute-defined-outside-init

    def end_serialization(self):
        pass


class SingleFeatureTrackingDataSerializer(BaseFeatureTrackingDataSerializer):
    def serialize(self, queryset, *args, **kwargs):  # pylint:disable=arguments-differ
        if queryset.count() != 1:
            raise SerializationError
        return super().serialize(queryset, *args, **kwargs)


class MultiFeatureTrackingDataSerializer(BaseFeatureTrackingDataSerializer):
    def serialize(self, queryset, *args, **kwargs):  # pylint:disable=arguments-differ
        if not isinstance(queryset, list):
            queryset = [queryset]
        return super().serialize(queryset, *args, **kwargs)


def render_filtered_point_features(shipment, tracking_data):
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

    return TrackingDataSerializer().serialize(
        tracking_data,
        geometry_field='point',
        fields=('uncertainty', 'source', 'time')
    )


def render_point_feature(tracking_data):
    """
    :param tracking_data: a TrackingData object
    :return: A single GeoJSON Point Feature representing tracking_data
    """
    return SingleFeatureTrackingDataSerializer().serialize(
        tracking_data,
        geometry_field='point',
        fields=('uncertainty', 'source', 'time')
    )
