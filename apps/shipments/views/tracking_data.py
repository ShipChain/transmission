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

from django.conf import settings
from influxdb_metrics.loader import log_metric
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from ..models import Shipment
from ..serializers import SignedDevicePayloadSerializer, UnvalidatedDevicePayloadSerializer, \
    PermissionLinkSerializer, TelemetryDataToDbSerializer, TrackingDataToDbSerializer
from ..tasks import tracking_data_update, telemetry_data_update

LOG = logging.getLogger('transmission')


class DeviceViewSet(viewsets.ViewSet):
    permission_classes = permissions.AllowAny
    serializer_class = PermissionLinkSerializer

    def _validate_payload(self, request, pk):
        shipment = Shipment.objects.filter(device_id=pk).first()

        if not shipment:
            LOG.debug(f'No shipment found associated to device: {pk}')
            raise PermissionDenied('No shipment found associated to device.')

        data = request.data
        serializer = (UnvalidatedDevicePayloadSerializer if settings.ENVIRONMENT in ('LOCAL', 'INT')
                      else SignedDevicePayloadSerializer)

        if not isinstance(data, list):
            LOG.debug(f'Adding data for device: {pk} for shipment: {shipment.id}')
            serializer = serializer(data=data, context={'shipment': shipment})
            serializer.is_valid(raise_exception=True)
            tracking_data = [serializer.validated_data]
        else:
            LOG.debug(f'Adding bulk data for device: {pk} shipment: {shipment.id}')
            serializer = serializer(data=data, context={'shipment': shipment}, many=True)
            serializer.is_valid(raise_exception=True)
            tracking_data = serializer.validated_data

        return shipment, tracking_data

    @action(detail=True, methods=['post'], permission_classes=(permissions.AllowAny,))
    def tracking(self, request, version, pk):
        LOG.debug(f'Adding tracking data by device with id: {pk}.')
        log_metric('transmission.info', tags={'method': 'devices.tracking', 'module': __name__})

        shipment, tracking_data = self._validate_payload(request, pk)

        for data in tracking_data:
            payload = data['payload']

            # Add tracking data to shipment via Engine RPC
            tracking_data_update.delay(shipment.id, payload)

            # Cache tracking data to db
            tracking_model_serializer = TrackingDataToDbSerializer(data=payload, context={'shipment': shipment,
                                                                                          'device': shipment.device})
            tracking_model_serializer.is_valid(raise_exception=True)
            tracking_model_serializer.save()

        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=['post'], permission_classes=(permissions.AllowAny,))
    def telemetry(self, request, version, pk):
        LOG.debug(f'Adding telemetry data by device with id: {pk}.')
        log_metric('transmission.info', tags={'method': 'devices.telemetry', 'module': __name__})

        shipment, telemetry_data = self._validate_payload(request, pk)

        for data in telemetry_data:
            payload = data['payload']

            # Add telemetry data to shipment via Engine RPC
            telemetry_data_update.delay(shipment.id, payload)

            # Cache telemetry data to db
            telemetry_model_serializer = TelemetryDataToDbSerializer(data=payload, context={'shipment': shipment,
                                                                                            'device': shipment.device})
            telemetry_model_serializer.is_valid(raise_exception=True)
            telemetry_model_serializer.save()

        return Response(status=status.HTTP_204_NO_CONTENT)
