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
from json.decoder import JSONDecodeError

import requests
from django.conf import settings
from influxdb_metrics.loader import log_metric
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, MethodNotAllowed, ValidationError
from rest_framework.views import APIView
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response
from shipchain_common.exceptions import Custom500Error

from apps.shipments.models import Device
from apps.shipments.permissions import IsOwnerOrShared
from apps.shipments.serializers import SignedDevicePayloadSerializer, UnvalidatedDevicePayloadSerializer, \
    PermissionLinkSerializer, TelemetryDataToDbSerializer, TrackingDataToDbSerializer
from apps.shipments.tasks import tracking_data_update, telemetry_data_update

LOG = logging.getLogger('transmission')


class DeviceViewSet(viewsets.ViewSet):
    permission_classes = permissions.AllowAny
    serializer_class = PermissionLinkSerializer

    @staticmethod
    def _validate_payload(request, pk):

        device = Device.objects.filter(pk=pk).first()

        # Determine the appropriate entity this payload applies to
        if device and hasattr(device, 'shipment'):
            associated_entity = device.shipment
            associated_entity_type = 'shipment'

        elif device and hasattr(device, 'route'):
            associated_entity = device.route
            associated_entity_type = 'route'

        else:
            LOG.debug(f'No shipment/route found associated to device: {pk}')
            raise PermissionDenied('No shipment/route found associated to device.')

        data = request.data
        serializer = (UnvalidatedDevicePayloadSerializer if settings.ENVIRONMENT in ('LOCAL', 'INT')
                      else SignedDevicePayloadSerializer)

        if not isinstance(data, list):
            LOG.debug(f'Adding data for device: {pk} for {associated_entity_type}: {associated_entity.id}')
            serializer = serializer(data=data, context={'associated_entity': associated_entity,
                                                        'associated_entity_type': associated_entity_type})
            serializer.is_valid(raise_exception=True)
            payload = [serializer.validated_data]
        else:
            LOG.debug(f'Adding bulk data for device: {pk} {associated_entity_type}: {associated_entity.id}')
            serializer = serializer(data=data, context={'associated_entity': associated_entity,
                                                        'associated_entity_type': associated_entity_type}, many=True)
            serializer.is_valid(raise_exception=True)
            payload = serializer.validated_data

        return associated_entity, associated_entity_type, payload

    @staticmethod
    def _save_payload(associated_entity, associated_entity_type, payload_list, delay_task, serializer_class):

        for data in payload_list:
            payload = data['payload']

            # Add tracking data to shipment via Engine RPC
            if associated_entity_type == 'route':
                for leg in associated_entity.routeleg_set.all():
                    delay_task.delay(leg.shipment.id, payload)
            else:
                delay_task.delay(associated_entity.id, payload)

            # Cache tracking data to db
            serializer = serializer_class(
                data=payload,
                context={associated_entity_type: associated_entity, 'device': associated_entity.device})

            serializer.is_valid(raise_exception=True)
            serializer.save()

    @action(detail=True, methods=['post'], permission_classes=(permissions.AllowAny,))
    def tracking(self, request, version, pk):
        LOG.debug(f'Adding tracking data by device with id: {pk}.')
        log_metric('transmission.info', tags={'method': 'devices.tracking', 'module': __name__})

        associated_entity, associated_entity_type, tracking_data = DeviceViewSet._validate_payload(request, pk)

        if associated_entity_type == 'shipment':
            serializer_class = TrackingDataToDbSerializer
        elif associated_entity_type == 'route':
            raise NotImplementedError
            # serializer_class = None
        else:
            raise ValidationError('Unable to determine entity associated to device')

        DeviceViewSet._save_payload(associated_entity, associated_entity_type,
                                    tracking_data, tracking_data_update,
                                    serializer_class)

        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=['post'], permission_classes=(permissions.AllowAny,))
    def telemetry(self, request, version, pk):
        LOG.debug(f'Adding telemetry data by device with id: {pk}.')
        log_metric('transmission.info', tags={'method': 'devices.telemetry', 'module': __name__})

        associated_entity, associated_entity_type, telemetry_data = DeviceViewSet._validate_payload(request, pk)

        if associated_entity_type == 'shipment':
            serializer_class = TelemetryDataToDbSerializer
        elif associated_entity_type == 'route':
            raise NotImplementedError
            # serializer_class = None
        else:
            raise ValidationError('Unable to determine entity associated to device')

        DeviceViewSet._save_payload(associated_entity, associated_entity_type,
                                    telemetry_data, telemetry_data_update,
                                    serializer_class)

        return Response(status=status.HTTP_204_NO_CONTENT)


class SensorViewset(APIView):
    permission_classes = ((IsOwnerOrShared, ) if settings.PROFILES_ENABLED else (permissions.AllowAny, ))

    renderer_classes = (JSONRenderer,)

    def get_serializer_class(self):
        pass

    def get(self, request, *args, **kwargs):
        pk = self.kwargs['device_pk']
        LOG.debug(f'Retrieving sensors for device with id: {pk}.')
        log_metric('transmission.info', tags={'method': 'devices.sensors', 'module': __name__})

        if not settings.PROFILES_ENABLED:
            raise MethodNotAllowed('sensors', detail='Unable to list sensors when not profiles is not enabled.')

        try:
            response = requests.get(
                f'{settings.PROFILES_URL}/api/v1/device/{pk}/sensor',
                params=request.query_params.dict()
            )
        except ConnectionError:
            raise Custom500Error(detail="Connection error when retrieving data from profiles.", status_code=503)

        try:
            response_json = response.json()
        except JSONDecodeError:
            raise Custom500Error(detail="Invalid response returned from profiles.", status_code=503)

        if response.status_code == 200:
            response_json['links'] = {k: v.replace(settings.PROFILES_URL, settings.INTERNAL_URL) if v else v
                                      for k, v in response_json['links'].items()}

        return Response(data=response_json, status=response.status_code)
