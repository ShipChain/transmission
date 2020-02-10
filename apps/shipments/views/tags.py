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

from django.conf import settings
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, permissions
from shipchain_common import mixins
from shipchain_common.permissions import HasViewSetActionPermissions
from shipchain_common.viewsets import ActionConfiguration, ConfigurableGenericViewSet

from apps.permissions import ShipmentExists, IsOwnerShipperCarrierModerator
from ..models import ShipmentTag
from ..serializers import ShipmentTagSerializer, ShipmentTagCreateSerializer


class ShipmentTagViewSet(mixins.ConfigurableCreateModelMixin,
                          mixins.ConfigurableRetrieveModelMixin,
                          mixins.ConfigurableListModelMixin,
                          ConfigurableGenericViewSet):

    queryset = ShipmentTag.objects.all()

    serializer_class = ShipmentTagSerializer

    permission_classes = (
        (permissions.IsAuthenticated,
         ShipmentExists,
         HasViewSetActionPermissions,
         IsOwnerShipperCarrierModerator, ) if settings.PROFILES_ENABLED else
        (permissions.AllowAny, ShipmentExists, )
    )

    # filter_backends = (filters.SearchFilter, filters.OrderingFilter, DjangoFilterBackend, )
    # ordering_fields = ('created_at', )
    # search_fields = ('name', )

    configuration = {
        'create': ActionConfiguration(
            request_serializer=ShipmentTagCreateSerializer,
            response_serializer=ShipmentTagSerializer
        ),
        'list': ActionConfiguration(response_serializer=ShipmentTagSerializer)
    }

    def get_queryset(self):
        return self.queryset.filter(shipment_id=self.kwargs['shipment_pk'])

    def perform_create(self, serializer):
        if settings.PROFILES_ENABLED:
            return serializer.save(user_id=self.request.user.id, shipment_id=self.kwargs['shipment_pk'])

        return serializer.save(shipment_id=self.kwargs['shipment_pk'])
