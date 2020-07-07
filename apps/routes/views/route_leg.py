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

from django.conf import settings
from django.db.models import Q
from rest_framework import permissions
from rest_framework.exceptions import ValidationError
from shipchain_common.mixins import mixins as cgvs_mixins
from shipchain_common.viewsets import ConfigurableGenericViewSet, ActionConfiguration

from apps.permissions import get_user
from apps.routes.models import RouteLeg
from apps.routes.permissions import NestedRoutePermission
from apps.routes.serializers import RouteLegCreateSerializer, RouteLegInfoSerializer
from apps.shipments.models import TransitState

LOG = logging.getLogger('transmission')


class RouteLegViewSet(cgvs_mixins.CreateModelMixin,
                      cgvs_mixins.DestroyModelMixin,
                      ConfigurableGenericViewSet):
    queryset = RouteLeg.objects.all()
    serializer_class = RouteLegInfoSerializer
    permission_classes = ((permissions.IsAuthenticated, NestedRoutePermission) if settings.PROFILES_ENABLED
                          else (permissions.AllowAny, NestedRoutePermission))

    configuration = {
        'create': ActionConfiguration(
            request_serializer=RouteLegCreateSerializer,
            response_serializer=RouteLegInfoSerializer,
        )
    }

    def get_queryset(self):
        queryset = self.queryset.filter(route__id=self.kwargs['route_pk'])

        if settings.PROFILES_ENABLED:
            user_id, organization_id = get_user(self.request)

            queryset_filter = Q(route__owner_id=user_id)
            if organization_id:
                queryset_filter |= Q(route__owner_id=organization_id)

            queryset = queryset.filter(queryset_filter)

        return queryset

    def perform_destroy(self, instance):
        if instance.route.routeleg_set.filter(shipment__state__gt=TransitState.AWAITING_PICKUP.value).exists():
            raise ValidationError(f'Cannot remove shipment from route after transit has begun')
        return super().perform_destroy(instance)
