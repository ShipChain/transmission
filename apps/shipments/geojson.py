import logging
from datetime import datetime

from rest_framework.exceptions import APIException
from geojson import Feature, FeatureCollection, LineString, Point

LOG = logging.getLogger('transmission')


def build_line_string_feature(shipment, tracking_data):
    """
    :param shipment: Shipment to be used for datetime filtering
    :param tracking_data: List of tracking data points returned from Engine
    :return: All tracking coordinates in a single GeoJSON LineString Feature
    """
    begin = (shipment.pickup_actual or datetime.min).replace(tzinfo=None)
    end = (shipment.delivery_actual or datetime.max).replace(tzinfo=None)
    tracking_points = []
    for point in tracking_data:
        try:
            dtp = DeviceTrackingPoint(point)
            if begin <= dtp.timestamp <= end:
                tracking_points.append(dtp)
        except InvalidTrackingPointError as err:
            LOG.warning(f'Error parsing tracking data for shipment {shipment.id}: {err}')

    return [DeviceTrackingPoint.get_linestring_feature(tracking_points)]


def build_point_features(shipment, tracking_data):
    """
    :param shipment: Shipment to be used for datetime filtering
    :param tracking_data: List of tracking data points returned from Engine
    :return: All tracking coordinates each in their own GeoJSON Point Feature
    """
    begin = (shipment.pickup_actual or datetime.min).replace(tzinfo=None)
    end = (shipment.delivery_actual or datetime.max).replace(tzinfo=None)
    point_features = []
    for point in tracking_data:
        try:
            dtp = DeviceTrackingPoint(point)
            if begin <= dtp.timestamp <= end:
                point_features.append(dtp.as_point_feature())
        except InvalidTrackingPointError as err:
            LOG.warning(f'Error parsing tracking data for shipment {shipment.id}: {err}')
    return point_features


def build_feature_collection(features):
    """
    :param features: List of Features, or single Feature to be returned in a FeatureCollection
    :return: All provided Features in a single FeatureCollection
    """
    feature_list = features

    if not isinstance(feature_list, list):
        feature_list = [feature_list]

    return FeatureCollection(feature_list)


class InvalidTrackingPointError(APIException):
    """
    Extend DRF APIException so these are automatically transformed via the exception handler
    """
    pass


class DeviceTrackingPoint(object):
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

        except IndexError:
            raise InvalidTrackingPointError(f"Invalid Coordinates format from device")

        except KeyError as key_error:
            raise InvalidTrackingPointError(f"Missing field {key_error} in tracking data from device")

    def as_point(self):
        try:
            return Point((self.lon, self.lat))
        except Exception:
            raise InvalidTrackingPointError("Unable to build GeoJSON Point from tracking data")

    def as_point_feature(self):
        try:
            return Feature(geometry=self.as_point(), properties={
                "time": self.timestamp,
                "uncertainty": self.uncertainty,
                "has_gps": self.has_gps,
                "source": self.source,
            })
        except Exception:
            raise InvalidTrackingPointError("Unable to build GeoJSON Point Feature from tracking data")

    @staticmethod
    def get_linestring_list(tracking_points):
        linestring = LineString([(point.lon, point.lat) for point in tracking_points])
        linestring_timestamps = [point.timestamp for point in tracking_points]

        return linestring, linestring_timestamps

    @staticmethod
    def get_linestring_feature(tracking_points):
        try:
            linestring, linestring_timestamps = DeviceTrackingPoint.get_linestring_list(tracking_points)
            return Feature(geometry=linestring, properties={"linestringTimestamps": linestring_timestamps})

        except Exception:
            raise InvalidTrackingPointError("Unable to build GeoJSON LineString Feature from tracking data")

    @staticmethod
    def __extract_date_fields(date):
        day, month, year = int(date[:2]), int(date[2:4]), int("20" + date[4:6])
        return day, month, year

    @staticmethod
    def __extract_time_fields(time):
        hour, minute, second = int(time[:2]), int(time[2:4]), int(time[4:6])
        return hour, minute, second

    @staticmethod
    def __build_timestamp(date, time):
        try:
            day, month, year = DeviceTrackingPoint.__extract_date_fields(date)
            hour, minute, second = DeviceTrackingPoint.__extract_time_fields(time)
            return datetime(year, month, day, hour, minute, second)

        except Exception as exception:
            raise InvalidTrackingPointError(f"Error building timestamp from device tracking data: '{exception}'")
