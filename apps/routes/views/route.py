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
from rest_framework import permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from shipchain_common.mixins import SerializationType
from shipchain_common.viewsets import ConfigurableModelViewSet, ActionConfiguration

from apps.permissions import get_owner_id, owner_access_filter
from apps.routes.models import Route
from apps.routes.serializers import RouteSerializer, RouteCreateSerializer, RouteUpdateSerializer, RouteOrderSerializer

LOG = logging.getLogger('transmission')


class RouteViewSet(ConfigurableModelViewSet):
    queryset = Route.objects.all()
    serializer_class = RouteSerializer
    permission_classes = ((permissions.IsAuthenticated,) if settings.PROFILES_ENABLED
                          else (permissions.AllowAny,))

    configuration = {
        'create': ActionConfiguration(
            request_serializer=RouteCreateSerializer,
            response_serializer=RouteSerializer,
        ),
        'update': ActionConfiguration(
            request_serializer=RouteUpdateSerializer,
            response_serializer=RouteSerializer,
        ),
        'retrieve': ActionConfiguration(
            serializer=RouteSerializer,
        ),
        'reorder': ActionConfiguration(
            request_serializer=RouteOrderSerializer,
            response_serializer=RouteSerializer,
        ),
    }

    def get_queryset(self):
        queryset = self.queryset

        if settings.PROFILES_ENABLED:
            queryset_filter = owner_access_filter(self.request)
            queryset = queryset.filter(queryset_filter)

        return queryset

    def perform_create(self, serializer):
        return serializer.save(owner_id=get_owner_id(self.request))

    @action(detail=True, methods=['post'], url_name='reorder')
    def reorder(self, request, version, pk):
        route = self.get_object()

        serializer = self.get_serializer(instance=route, data=request.data)
        serializer.is_valid(raise_exception=True)

        route.set_routeleg_order(serializer.validated_data['legs'])

        response = self.get_serializer(route, serialization_type=SerializationType.RESPONSE)
        return Response(response.data, status=status.HTTP_202_ACCEPTED)
