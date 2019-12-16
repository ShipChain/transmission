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
from rest_framework import permissions
from rest_framework.response import Response
from rest_framework.views import APIView

from ..models import Shipment
from ..permissions import IsShipmentOwner
from ..serializers import ShipmentSerializer, ShipmentActionRequestSerializer

LOG = logging.getLogger('transmission')


class ShipmentActionsView(APIView):
    resource_name = 'Shipment'
    permission_classes = ((IsShipmentOwner,) if settings.PROFILES_ENABLED else (permissions.AllowAny,))

    def post(self, request, *args, **kwargs):
        LOG.debug(f'Performing action on shipment with id: {kwargs["shipment_pk"]}.')
        log_metric('transmission.info', tags={'method': 'shipment.action', 'module': __name__})

        shipment = Shipment.objects.get(id=kwargs['shipment_pk'])
        serializer = ShipmentActionRequestSerializer(data=request.data, context={'shipment': shipment})
        serializer.is_valid(raise_exception=True)

        method = serializer.validated_data.pop('action_type')
        method.value(shipment, **serializer.validated_data)
        shipment.save()

        return Response(ShipmentSerializer(shipment).data)
