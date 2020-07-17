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

import logging

from dateutil.parser import parse
from rest_framework import exceptions, serializers as rest_serializers

from apps.routes.models import RouteTrackingData
from apps.routes.serializers import RouteSerializer

LOG = logging.getLogger('transmission')


class BaseRouteDataToDbSerializer(rest_serializers.ModelSerializer):
    route = RouteSerializer(read_only=True)

    def __init__(self, *args, **kwargs):
        # Ensure that the timestamps is valid
        try:
            kwargs['data']['timestamp'] = parse(kwargs['data']['timestamp'])
        except Exception as exception:
            raise exceptions.ValidationError(detail=f"Unable to parse tracking data timestamp in to datetime object: \
                                                    {exception}")

        super().__init__(*args, **kwargs)


class RouteTrackingDataToDbSerializer(BaseRouteDataToDbSerializer):
    """
    Serializer for tracking data to be cached in db
    """
    def __init__(self, *args, **kwargs):
        if 'position' not in kwargs['data']:
            raise exceptions.ValidationError(detail='Unable to find `position` field in body.')
        kwargs['data'].update(kwargs['data'].pop('position'))

        super().__init__(*args, **kwargs)

    class Meta:
        model = RouteTrackingData
        exclude = ('point', 'time', 'device')

    def create(self, validated_data):
        return RouteTrackingData.objects.create(**validated_data, **self.context)
