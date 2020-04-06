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

from django.conf import settings
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, permissions
from shipchain_common import mixins
from shipchain_common.permissions import HasViewSetActionPermissions
from shipchain_common.viewsets import ActionConfiguration, ConfigurableGenericViewSet

from apps.permissions import ShipmentExists, IsNestedOwnerShipperCarrierModerator
from ..models import ShipmentNote
from ..serializers import ShipmentNoteSerializer, ShipmentNoteCreateSerializer


class ShipmentNoteViewSet(mixins.ConfigurableCreateModelMixin,
                          mixins.ConfigurableRetrieveModelMixin,
                          mixins.ConfigurableListModelMixin,
                          ConfigurableGenericViewSet):

    queryset = ShipmentNote.objects.all()

    serializer_class = ShipmentNoteSerializer

    permission_classes = (
        (permissions.IsAuthenticated,
         ShipmentExists,
         HasViewSetActionPermissions,
         IsNestedOwnerShipperCarrierModerator, ) if settings.PROFILES_ENABLED else
        (permissions.AllowAny, ShipmentExists, )
    )

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
