"""
Copyright 2020 ShipChain, Inc.

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

from rest_framework import serializers

from apps.routes.models import RouteTelemetryData
from apps.routes.serializers import BaseRouteDataToDbSerializer

LOG = logging.getLogger('transmission')


class RouteTelemetryDataToDbSerializer(BaseRouteDataToDbSerializer):
    """
    Serializer for telemetry data to be cached in db
    """
    class Meta:
        model = RouteTelemetryData
        exclude = ('device',)

    def create(self, validated_data):
        return RouteTelemetryData.objects.create(**validated_data, **self.context)


class RouteTelemetryResponseSerializer(serializers.ModelSerializer):
    """
    Serializer for telemetry data consumer
    """
    timestamp = serializers.DateTimeField()
    value = serializers.FloatField()

    class Meta:
        model = RouteTelemetryData
        fields = ('sensor_id', 'timestamp', 'hardware_id', 'value')


class RouteTelemetryResponseAggregateSerializer(RouteTelemetryResponseSerializer):
    timestamp = serializers.DateTimeField(source='window')
    value = serializers.FloatField(source='aggregate_value')
