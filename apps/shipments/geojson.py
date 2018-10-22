import logging
from datetime import datetime

from rest_framework.exceptions import APIException
from geojson import Feature, FeatureCollection, LineString, Point
from influxdb_metrics.loader import log_metric


LOG = logging.getLogger('transmission')


def build_line_string_feature(shipment, tracking_data):
    """
    :param shipment: Shipment to be used for datetime filtering
    :param tracking_data: List of tracking data points returned from Engine
    :return: All tracking coordinates in a single GeoJSON LineString Feature
    """
    begin = (shipment.pickup_actual or datetime.min).replace(tzinfo=None)
    end = (shipment.delivery_actual or datetime.max).replace(tzinfo=None)
    LOG.debug(f'Building line string feature for shipment {shipment.id}.')
    log_metric('transmission.info', tags={'method': 'build_line_string_feature', 'package': 'shipments.geojson'})
    tracking_points = []
    for point in tracking_data:
        try:
            dtp = DeviceTrackingPoint(point)
            if begin <= dtp.timestamp <= end:
                tracking_points.append(dtp)
        except APIException as err:
            LOG.warning(f'Error parsing tracking data for shipment {shipment.id}: {err}')
    tracking_points.sort(key=lambda dt_point: dt_point.timestamp)
    return [DeviceTrackingPoint.get_linestring_feature(tracking_points)]


def build_point_features(shipment, tracking_data):
    """
    :param shipment: Shipment to be used for datetime filtering
    :param tracking_data: List of tracking data points returned from Engine
    :return: All tracking coordinates each in their own GeoJSON Point Feature
    """
    begin = (shipment.pickup_actual or datetime.min).replace(tzinfo=None)
    end = (shipment.delivery_actual or datetime.max).replace(tzinfo=None)
    LOG.debug(f'Build point features with tracking_data {tracking_data}.')
    log_metric('transmission.info', tags={'method': 'build_point_features', 'package': 'shipments.geojson'})

    raw_points = []
    for point in tracking_data:
        try:
            dtp = DeviceTrackingPoint(point)
            if begin <= dtp.timestamp <= end:
                point_features.append(dtp.as_point_feature())
        except APIException as err:
            LOG.warning(f'Error parsing tracking data for shipment {shipment.id}: {err}')
    point_features.sort(key=lambda dt_feature: dt_feature.properties['time'])
    return point_features


def build_feature_collection(features):
    """
    :param features: List of Features, or single Feature to be returned in a FeatureCollection
    :return: All provided Features in a single FeatureCollection
    """
    LOG.debug(f'Build feature collection with features {features}.')
    log_metric('transmission.info', tags={'method': 'build_feature_collection', 'package': 'shipments.geojson'})

    feature_list = features

    if not isinstance(feature_list, list):
        feature_list = [feature_list]

    return FeatureCollection(feature_list)


class DeviceTrackingPoint:
    """
    Serialize the returned tracking data in to this class to catch formatting errors and assist in
    generating the appropriate GeoJSON Features correctly
    """

    def __init__(self, point):
        try:
            self.lat = point['coordinates'][0]
            self.lon = point['coordinates'][1]
            self.timestamp = DeviceTrackingPoint.__build_timestamp(point['fix_date'], point['fix_time'])

            self.uncertainty = point['uncertainty'] if 'uncertainty' in point else None
            self.has_gps = point['has_gps'] if 'has_gps' in point else None
            self.source = point['source'] if 'source' in point else None

        except IndexError as index_error:
            LOG.error(f'Device tracking index Error {index_error}.')
            log_metric('transmission.error', tags={'method': 'device_tracking_index_error',
                                                   'package': 'shipments.geojson', 'code': 'device_tracking_index'})

            raise APIException(detail=f"Invalid Coordinates format from device")

        except KeyError as key_error:
            LOG.error(f'Device tracking key Error {key_error}.')
            log_metric('transmission.error', tags={'method': 'device_tracking_key_error',
                                                   'package': 'shipments.geojson', 'code': 'device_tracking_key'})

            raise APIException(detail=f"Missing field {key_error} in tracking data from device")

    def as_point(self):
        LOG.debug(f'Device tracking as_point.')
        log_metric('transmission.info', tags={'method': 'as_point', 'package': 'shipments.geojson'})

        try:
            return Point((self.lon, self.lat))
        except Exception as exception:
            LOG.error(f'Device tracking as_point exception {exception}.')
            log_metric('transmission.error', tags={'method': 'as_point_exception',
                                                   'package': 'shipments.geojson', 'code': 'as_point'})

            raise APIException(detail="Unable to build GeoJSON Point from tracking data")

    def as_point_feature(self):
        LOG.debug(f'Device tracking as_point.')
        log_metric('transmission.info', tags={'method': 'as_point_feature', 'package': 'shipments.geojson'})

        try:
            return Feature(geometry=self.as_point(), properties={
                "time": self.timestamp,
                "uncertainty": self.uncertainty,
                "has_gps": self.has_gps,
                "source": self.source,
            })
        except Exception as exception:
            LOG.error(f'Device tracking as_point_feature exception {exception}.')
            log_metric('transmission.error', tags={'method': 'as_point_feature_exception',
                                                   'package': 'shipments.geojson', 'code': 'as_point_feature'})

            raise APIException(detail="Unable to build GeoJSON Point Feature from tracking data")

    @staticmethod
    def get_linestring_list(tracking_points):
        linestring = LineString([(point.lon, point.lat) for point in tracking_points])
        linestring_timestamps = [point.timestamp for point in tracking_points]

        return linestring, linestring_timestamps

    @staticmethod
    def get_linestring_feature(tracking_points):
        try:
            LOG.debug(f'Device tracking get_linestring_list with tracking points {tracking_points}.')
            log_metric('transmission.info', tags={'method': 'get_linestring_list', 'package': 'shipments.geojson'})

            linestring, linestring_timestamps = DeviceTrackingPoint.get_linestring_list(tracking_points)
            return Feature(geometry=linestring, properties={"linestringTimestamps": linestring_timestamps})

        except Exception as exception:
            LOG.error(f'Device tracking get_linestring_feature exception {exception}.')
            log_metric('transmission.error', tags={'method': 'get_linestring_feature'})

            raise APIException(detail="Unable to build GeoJSON LineString Feature from tracking data")

    @staticmethod
    def __extract_date_fields(date):
        LOG.debug(f'Device tracking __extract_date_fields with date {date}.')
        log_metric('transmission.info', tags={'method': '__extract_date_fields', 'package': 'shipments.geojson'})

        day, month, year = int(date[:2]), int(date[2:4]), int("20" + date[4:6])
        return day, month, year

    @staticmethod
    def __extract_time_fields(time):
        LOG.debug(f'Device tracking __extract_time_fields with time {time}.')
        log_metric('transmission.info', tags={'method': '__extract_time_fields', 'package': 'shipments.geojson'})

        hour, minute, second = int(time[:2]), int(time[2:4]), int(time[4:6])
        return hour, minute, second

    @staticmethod
    def __build_timestamp(date, time):
        LOG.debug(f'Device tracking __build_timestamp with date {date} and time {time}.')
        log_metric('transmission.info', tags={'method': '__build_timestamp', 'package': 'shipments.geojson'})

        try:
            day, month, year = DeviceTrackingPoint.__extract_date_fields(date)
            hour, minute, second = DeviceTrackingPoint.__extract_time_fields(time)
            return datetime(year, month, day, hour, minute, second)

        except Exception as exception:
            LOG.error(f'Device tracking __build_timestamp exception {exception}.')
            log_metric('transmission.error', tags={'method': '__build_timestamp_exception',
                                                   'package': 'shipments.geojson', 'code': '__build_timestamp'})

            raise APIException(detail=f"Error building timestamp from device tracking data: '{exception}'")
