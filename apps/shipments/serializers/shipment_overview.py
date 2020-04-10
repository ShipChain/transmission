"""
Copyright 2019 ShipChain, Inc.

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""

from rest_framework import exceptions
from rest_framework_json_api import serializers
from rest_framework_gis import serializers as geo_serializers

from ..models import TrackingData, Device
from ..serializers import ShipmentOverviewSerializer


class QueryParamsSerializer(serializers.Serializer):
    in_bbox = serializers.CharField(required=False, allow_null=True, default=None)

    def validate_in_bbox(self, in_bbox):
        long_range = (-180, 180)
        lat_range = (-90, 90)
        box_ranges = (long_range, lat_range, long_range, lat_range)

        if in_bbox:
            box_to_list = in_bbox.split(',')
            if not len(box_to_list) == 4:
                raise exceptions.ValidationError(f'in_box parameter takes 4 position parameters but '
                                                 f'{len(box_to_list)}, were passed in.')

            in_bbox_num = []
            for box_value, rang, index in zip(box_to_list, box_ranges, range(1, 5)):
                try:
                    box_value = float(box_value)
                    in_bbox_num.append(box_value)
                except ValueError:
                    raise exceptions.ValidationError(f'in_bbox coordinate: {box_value}, should be type number')

                if not rang[0] <= box_value <= rang[1]:
                    raise exceptions.ValidationError(f'in_bbox coordinate in position: '
                                                     f'{index}, value: {box_value}, should be in range: {rang}')

            if in_bbox_num[2] <= in_bbox_num[0] or in_bbox_num[3] <= in_bbox_num[1]:
                raise exceptions.ValidationError('Invalid geo box, make sure that: '
                                                 'in_bbox[1] < in_bbox[3] and in_bbox[2] < in_bbox[4].')

            return in_bbox_num
        return None


class FKDeviceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Device
        fields = ('id',)


class TrackingOverviewGeojsonSerializer(geo_serializers.GeoFeatureModelSerializer):
    class Meta:
        model = TrackingData
        fields = ('uncertainty', 'source', 'time')
        geo_field = 'point'


class TrackingOverviewSerializer(serializers.ModelSerializer):
    point = TrackingOverviewGeojsonSerializer(source='*')

    class Meta:
        model = TrackingData
        fields = ('point', 'device', 'shipment', )

    class JSONAPIMeta:
        included_resources = ('shipment', )

    included_serializers = {
        'shipment': ShipmentOverviewSerializer,
        'device': FKDeviceSerializer
    }
