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
from shipchain_common.permissions import HasViewSetActionPermissions
from shipchain_common.viewsets import ActionConfiguration, ConfigurableModelViewSet

from apps.permissions import ShipmentExists
from ..models import AccessRequest
from ..serializers import AccessRequestSerializer, AccessRequestCreateSerializer


class AccessRequestViewSet(ConfigurableModelViewSet):

    queryset = AccessRequest.objects.all()

    serializer_class = AccessRequestSerializer

    permission_classes = (
        (permissions.IsAuthenticated,
         ShipmentExists,
         HasViewSetActionPermissions,
         # TODO: IsRequester | CanApprove
         ) if settings.PROFILES_ENABLED else
        (permissions.AllowAny, ShipmentExists, )
    )

    filter_backends = (filters.SearchFilter, filters.OrderingFilter, DjangoFilterBackend, )
    filterset_fields = ('requester_id', 'approved', 'approved_by')
    ordering_fields = ('created_at', 'approved_at')

    configuration = {
        'create': ActionConfiguration(
            request_serializer=AccessRequestCreateSerializer,
            response_serializer=AccessRequestSerializer
        ),
    }

    def get_queryset(self):
        return self.queryset.filter(shipment_id=self.kwargs['shipment_pk'])
