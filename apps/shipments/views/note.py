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
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, permissions
from rest_framework_json_api import serializers
from shipchain_common import mixins
from shipchain_common.permissions import HasViewSetActionPermissions
from shipchain_common.viewsets import ActionConfiguration, ConfigurableGenericViewSet

from apps.permissions import UserHasShipmentPermission
from ..models import ShipmentNote, Shipment
from ..serializers import ShipmentNoteSerializer, ShipmentNoteCreateSerializer

LOG = logging.getLogger('transmission')


class ShipmentNoteViewSet(mixins.ConfigurableCreateModelMixin,
                          mixins.ConfigurableRetrieveModelMixin,
                          mixins.ConfigurableListModelMixin,
                          ConfigurableGenericViewSet):
    queryset = ShipmentNote.objects.all()
    serializer_class = ShipmentNoteSerializer
    permission_classes = ((permissions.IsAuthenticated, HasViewSetActionPermissions, UserHasShipmentPermission, )
                          if settings.PROFILES_ENABLED else (permissions.AllowAny, ))
    filter_backends = (filters.SearchFilter, filters.OrderingFilter, DjangoFilterBackend, )
    filterset_fields = ('user_id', )
    ordering_fields = ('created_at', )
    search_fields = ('message', )

    configuration = {
        'create': ActionConfiguration(
            request_serializer=ShipmentNoteCreateSerializer,
            response_serializer=ShipmentNoteSerializer
        ),
        'list': ActionConfiguration(response_serializer=ShipmentNoteSerializer)
    }

    def get_queryset(self):
        return self.queryset.filter(shipment_id=self.kwargs['shipment_pk'])

    def perform_create(self, serializer):
        if settings.PROFILES_ENABLED:
            created = serializer.save(user_id=self.request.user.id, shipment_id=self.kwargs['shipment_pk'])
        else:
            try:
                # We ensure that the provided shipment exists when profiles is disabled
                Shipment.objects.get(id=self.kwargs['shipment_pk'])
            except Shipment.DoesNotExist:
                raise serializers.ValidationError('Invalid shipment provided')

            created = serializer.save(shipment_id=self.kwargs['shipment_pk'])
        return created
