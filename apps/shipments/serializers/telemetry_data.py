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
from datetime import datetime, timezone

from dateutil.parser import parse
from django.core.serializers import serialize
from influxdb_metrics.loader import log_metric
from rest_framework import exceptions, serializers as rest_serializers

from apps.shipments.models import TelemetryData
from . import ShipmentSerializer

LOG = logging.getLogger('transmission')


class TelemetryDataToDbSerializer(rest_serializers.ModelSerializer):
    """
    Serializer for tracking data to be cached in db
    """
    shipment = ShipmentSerializer(read_only=True)

    def __init__(self, *args, **kwargs):
        # Ensure that the timestamps is valid
        try:
            kwargs['data']['timestamp'] = parse(kwargs['data']['timestamp'])
        except Exception as exception:
            raise exceptions.ValidationError(detail=f"Unable to parse tracking data timestamp in to datetime object: \
                                                    {exception}")

        super().__init__(*args, **kwargs)

    class Meta:
        model = TelemetryData
        exclude = ('device',)

    def create(self, validated_data):
        return TelemetryData.objects.create(**validated_data, **self.context)


def render_filtered_telemetry(shipment, telemetry):
    """
    :param shipment: Shipment to be used for datetime filtering
    :param tracking_data: queryset of TrackingData objects
    :return: All tracking coordinates each in their own GeoJSON Point Feature
    """
    log_metric('transmission.info', tags={'method': 'render_filtered_telemetry', 'module': __name__})
    LOG.debug(f'Rendering filtered telemetry for shipment: {shipment.id}.')

    begin = (shipment.pickup_act or datetime.min).replace(tzinfo=timezone.utc)
    end = (shipment.delivery_act or datetime.max).replace(tzinfo=timezone.utc)

    telemetry = telemetry.filter(timestamp__range=(begin, end))

    return serialize(
        'json',
        telemetry,
        fields=["timestamp", "hardware_id", "sensor_id", "value"]
    )
