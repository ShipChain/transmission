import logging
from datetime import datetime

from rest_framework.exceptions import APIException
from geojson import FeatureCollection
from influxdb_metrics.loader import log_metric


LOG = logging.getLogger('transmission')


def build_line_string_feature(shipment, tracking_data):
    """
    :param shipment: Shipment to be used for datetime filtering
    :param tracking_data: queryset of TrackingData objects
    :return: All tracking coordinates in a single GeoJSON LineString Feature
    """
    begin = (shipment.pickup_actual or datetime.min).replace(tzinfo=None)
    end = (shipment.delivery_actual or datetime.max).replace(tzinfo=None)
    LOG.debug(f'Building line string feature for shipment {shipment.id}.')
    log_metric('transmission.info', tags={'method': 'build_line_string_feature', 'module': __name__})

    tracking_points = []
    for point in tracking_data:
        try:
            if begin <= point.datetime_timestamp <= end:
                tracking_points.append(point)
        except APIException as err:
            LOG.warning(f'Error parsing tracking data for shipment {shipment.id}: {err}')

    tracking_points.sort(key=lambda dt_point: dt_point.datetime_timestamp)

    return [tracking_points[0].get_linestring_feature(tracking_points)]


def build_point_features(shipment, tracking_data):
    """
    :param shipment: Shipment to be used for datetime filtering
    :param tracking_data: queryset of TrackingData objects
    :return: All tracking coordinates each in their own GeoJSON Point Feature
    """
    begin = (shipment.pickup_actual or datetime.min).replace(tzinfo=None)
    end = (shipment.delivery_actual or datetime.max).replace(tzinfo=None)
    LOG.debug(f'Build point features with tracking_data {tracking_data}.')
    log_metric('transmission.info', tags={'method': 'build_point_features', 'module': __name__})

    raw_points = []
    for point in tracking_data:
        try:
            if begin <= point.datetime_timestamp <= end:
                raw_points.append(point)
        except APIException as err:
            LOG.warning(f'Error parsing tracking data for shipment {shipment.id}: {err}')

    raw_points.sort(key=lambda p: p.datetime_timestamp)

    return [p.as_point_feature for p in raw_points]


def build_feature_collection(features):
    """
    :param features: List of Features, or single Feature to be returned in a FeatureCollection
    :return: All provided Features in a single FeatureCollection
    """
    LOG.debug(f'Build feature collection with features {features}.')
    log_metric('transmission.info', tags={'method': 'build_feature_collection', 'module': __name__})

    feature_list = features

    if not isinstance(feature_list, list):
        feature_list = [feature_list]

    return FeatureCollection(feature_list)
