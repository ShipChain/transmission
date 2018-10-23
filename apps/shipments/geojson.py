import logging
from datetime import datetime

from rest_framework.exceptions import APIException
from geojson import Feature, FeatureCollection, LineString, Point
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
            dtp = DeviceTrackingPoint(point)
            if begin <= dtp.timestamp <= end:
                raw_points.append(dtp)
        except APIException as err:
            LOG.warning(f'Error parsing tracking data for shipment {shipment.id}: {err}')

    raw_points.sort(key=lambda p: p.timestamp)
    point_features = [p.as_point_feature() for p in raw_points]

    return point_features


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


class DeviceTrackingPoint:
    """
    Serialize the returned tracking data in to this class to catch formatting errors and assist in
    generating the appropriate GeoJSON Features correctly
    :param point: Instance of TrackingData from database
    """

    def __init__(self, point):
        try:
            self.lat = point.latitude
            self.lon = point.longitude
            self.raw_timestamp = point.timestamp
            self.uncertainty = point.uncertainty
            self.has_gps = True if point.source == 'gps' else False
            self.source = point.source

        except IndexError as index_error:
            LOG.error(f'Device tracking index Error {index_error}.')
            log_metric('transmission.error', tags={'method': 'device_tracking_index_error',
                                                   'module': __name__, 'code': 'device_tracking_index'})

            raise APIException(detail=f"Invalid Coordinates format from device")

        except KeyError as key_error:
            LOG.error(f'Device tracking key Error {key_error}.')
            log_metric('transmission.error', tags={'method': 'device_tracking_key_error',
                                                   'module': __name__, 'code': 'device_tracking_key'})

            raise APIException(detail=f"Missing field {key_error} in tracking data from device")

    def as_point(self):
        LOG.debug(f'Device tracking as_point.')
        log_metric('transmission.info', tags={'method': 'as_point', 'module': __name__})

        try:
            return Point((self.lon, self.lat))
        except Exception as exception:
            LOG.error(f'Device tracking as_point exception {exception}.')
            log_metric('transmission.error', tags={'method': 'as_point_exception',
                                                   'module': __name__, 'code': 'as_point'})

            raise APIException(detail="Unable to build GeoJSON Point from tracking data")

    def as_point_feature(self):
        LOG.debug(f'Device tracking as_point.')
        log_metric('transmission.info', tags={'method': 'as_point_feature', 'module': __name__})

        try:
            return Feature(geometry=self.as_point(), properties={
                "time": self.timestamp.isoformat(),
                "uncertainty": self.uncertainty,
                "has_gps": self.has_gps,
                "source": self.source,
            })
        except Exception as exception:
            LOG.error(f'Device tracking as_point_feature exception {exception}.')
            log_metric('transmission.error', tags={'method': 'as_point_feature_exception',
                                                   'module': __name__, 'code': 'as_point_feature'})

            raise APIException(detail="Unable to build GeoJSON Point Feature from tracking data")

    @property
    def timestamp(self):
        date = self.raw_timestamp[:10]
        time = self.raw_timestamp[11:19]
        return self.__build_timestamp(date, time)

    @property
    def timestamp_str(self):
        return self.timestamp.isoformat()

    @staticmethod
    def get_linestring_list(tracking_points):
        linestring = LineString([(point.lon, point.lat) for point in tracking_points])
        linestring_timestamps = [point.timestamp_str for point in tracking_points]

        return linestring, linestring_timestamps

    @staticmethod
    def get_linestring_feature(tracking_points):
        try:
            LOG.debug(f'Device tracking get_linestring_list with tracking points {tracking_points}.')
            log_metric('transmission.info', tags={'method': 'get_linestring_list', 'module': __name__})

            linestring, linestring_timestamps = DeviceTrackingPoint.get_linestring_list(tracking_points)
            return Feature(geometry=linestring, properties={"linestringTimestamps": linestring_timestamps})

        except Exception as exception:
            LOG.error(f'Device tracking get_linestring_feature exception {exception}.')
            log_metric('transmission.error', tags={'method': 'get_linestring_feature', 'module': __name__})

            raise APIException(detail="Unable to build GeoJSON LineString Feature from tracking data")

    @staticmethod
    def __extract_date_fields(date):
        LOG.debug(f'Device tracking __extract_date_fields with date {date}.')
        log_metric('transmission.info', tags={'method': '__extract_date_fields', 'module': __name__})

        year, month, day = int(date[:4]), int(date[5:7]), int(date[8:10])
        return day, month, year

    @staticmethod
    def __extract_time_fields(time):
        LOG.debug(f'Device tracking __extract_time_fields with time {time}.')
        log_metric('transmission.info', tags={'method': '__extract_time_fields', 'module': __name__})

        hour, minute, second = int(time[:2]), int(time[3:5]), int(time[6:8])
        return hour, minute, second

    @staticmethod
    def __build_timestamp(date, time):
        LOG.debug(f'Device tracking __build_timestamp with date {date} and time {time}.')
        log_metric('transmission.info', tags={'method': '__build_timestamp', 'module': __name__})

        try:
            day, month, year = DeviceTrackingPoint.__extract_date_fields(date)
            hour, minute, second = DeviceTrackingPoint.__extract_time_fields(time)
            return datetime(year, month, day, hour, minute, second)

        except Exception as exception:
            LOG.error(f'Device tracking __build_timestamp exception {exception}.')
            log_metric('transmission.error', tags={'method': '__build_timestamp_exception',
                                                   'module': __name__, 'code': '__build_timestamp'})

            raise APIException(detail=f"Error building timestamp from device tracking data: '{exception}'")
