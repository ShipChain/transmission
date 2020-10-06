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
from string import Template

from django.conf import settings
from django.db.models import Q
from django.http import HttpResponse
from django.utils.decorators import method_decorator
from django_filters.rest_framework import DjangoFilterBackend
from fancy_cache import cache_page
from influxdb_metrics.loader import log_metric
from rest_framework import permissions, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from shipchain_common.mixins import SerializationType
from shipchain_common.permissions import HasViewSetActionPermissions
from shipchain_common.utils import parse_value
from shipchain_common.viewsets import ActionConfiguration, ConfigurableModelViewSet

from apps.jobs.models import JobState
from apps.permissions import owner_access_filter, get_owner_id, IsOwner, ShipmentExists, ORRequestResult
from ..filters import ShipmentFilter, SHIPMENT_SEARCH_FIELDS, SHIPMENT_ORDERING_FIELDS
from ..geojson import render_filtered_point_features
from ..models import Shipment, TrackingData, PermissionLink, TransitState, PermissionLevel, AccessRequest, Endpoints
from ..permissions import IsOwnerOrShared, IsOwnerShipperCarrierModerator, shipment_list_wallets_filter
from ..serializers import ShipmentSerializer, ShipmentCreateSerializer, ShipmentUpdateSerializer, \
    ShipmentTxSerializer
from ...routes.models import RouteTrackingData

LOG = logging.getLogger('transmission')


UPDATE_PERMISSION_CLASSES = (
    (HasViewSetActionPermissions,
     ShipmentExists,
     ORRequestResult(IsOwnerShipperCarrierModerator,
                     AccessRequest.permission(Endpoints.shipment, PermissionLevel.READ_WRITE))
     ) if settings.PROFILES_ENABLED else (permissions.AllowAny, ShipmentExists,)
)

RETRIEVE_PERMISSION_CLASSES = (
    (ShipmentExists,
     ORRequestResult(IsOwnerOrShared,
                     AccessRequest.permission(Endpoints.shipment, PermissionLevel.READ_ONLY)),
     ) if settings.PROFILES_ENABLED else (permissions.AllowAny, ShipmentExists, )
)


DELETE_PERMISSION_CLASSES = ((permissions.IsAuthenticated, IsOwner, ) if settings.PROFILES_ENABLED
                             else (permissions.AllowAny, ))


class ShipmentViewSet(ConfigurableModelViewSet):
    # We need to revisit the ConfigurableGenericViewSet to ensure
    # that it properly allow the inheritance of this attribute
    resource_name = 'Shipment'

    queryset = Shipment.objects.all()

    serializer_class = ShipmentSerializer

    permission_classes = ((HasViewSetActionPermissions,
                           IsOwnerOrShared, ) if settings.PROFILES_ENABLED else (permissions.AllowAny, ))

    filter_backends = (filters.SearchFilter, filters.OrderingFilter, DjangoFilterBackend, )

    filterset_class = ShipmentFilter

    search_fields = SHIPMENT_SEARCH_FIELDS

    ordering_fields = SHIPMENT_ORDERING_FIELDS

    http_method_names = ['get', 'post', 'delete', 'patch']

    configuration = {
        'create': ActionConfiguration(
            request_serializer=ShipmentCreateSerializer,
            response_serializer=ShipmentTxSerializer,
        ),
        'update': ActionConfiguration(
            request_serializer=ShipmentUpdateSerializer,
            response_serializer=ShipmentTxSerializer,
            permission_classes=UPDATE_PERMISSION_CLASSES
        ),
        'retrieve': ActionConfiguration(
            permission_classes=RETRIEVE_PERMISSION_CLASSES
        ),
        'destroy': ActionConfiguration(
            permission_classes=DELETE_PERMISSION_CLASSES
        ),
    }

    def get_queryset(self):
        queryset = self.queryset
        if settings.PROFILES_ENABLED:
            queryset_filter = owner_access_filter(self.request)

            permission_link = self.request.query_params.get('permission_link')
            if permission_link:
                # The  validity of the permission link object has already been done by the permission class
                queryset_filter = queryset_filter | Q(pk=PermissionLink.objects.get(pk=permission_link).shipment.pk)

            elif self.detail:
                return queryset

            else:
                queryset_filter = queryset_filter | shipment_list_wallets_filter(self.request)

            queryset = queryset.filter(queryset_filter)

        queryset = self._parse_customer_fields_queries(queryset)

        return queryset

    def _parse_customer_fields_queries(self, queryset):
        for key, value in self.request.query_params.items():
            if key.startswith('customer_fields__'):
                queryset = queryset.filter(**{key: parse_value(value)})

        return queryset

    def perform_create(self, serializer):
        if settings.PROFILES_ENABLED:
            background_data_hash_interval = self.request.user.token.get('background_data_hash_interval',
                                                                        settings.DEFAULT_BACKGROUND_DATA_HASH_INTERVAL)
            manual_update_hash_interval = self.request.user.token.get('manual_update_hash_interval',
                                                                      settings.DEFAULT_MANUAL_UPDATE_HASH_INTERVAL)
            created = serializer.save(owner_id=get_owner_id(self.request), updated_by=self.request.user.id,
                                      background_data_hash_interval=background_data_hash_interval,
                                      manual_update_hash_interval=manual_update_hash_interval)
        else:
            created = serializer.save(background_data_hash_interval=settings.DEFAULT_BACKGROUND_DATA_HASH_INTERVAL,
                                      manual_update_hash_interval=settings.DEFAULT_MANUAL_UPDATE_HASH_INTERVAL)
        return created

    def perform_update(self, serializer):
        return serializer.save(updated_by=self.request.user.id)

    def create(self, request, *args, **kwargs):
        """
        Create a Shipment object and make Async Request to Engine
        """
        LOG.debug('Creating a shipment object.')
        log_metric('transmission.info', tags={'method': 'shipments.create', 'module': __name__})
        # Create Shipment
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        shipment = self.perform_create(serializer)
        async_job = shipment.asyncjob_set.all()[:1]

        response = self.get_serializer(shipment, serialization_type=SerializationType.RESPONSE)
        if async_job:
            LOG.debug(f'AsyncJob created with id {async_job[0].id}.')
            response.instance.async_job_id = async_job[0].id

        return Response(response.data, status=status.HTTP_202_ACCEPTED)

    @method_decorator(cache_page(60 * 60, remember_all_urls=True))  # Cache responses for 1 hour
    @action(detail=True, methods=['get'], permission_classes=(
            ORRequestResult(IsOwnerOrShared, AccessRequest.permission(Endpoints.tracking, PermissionLevel.READ_ONLY)),))
    def tracking(self, request, version, pk):
        """
        Retrieve tracking data from db
        """
        LOG.debug(f'Retrieve tracking data for a shipment {pk}.')
        log_metric('transmission.info', tags={'method': 'shipments.tracking', 'module': __name__})
        shipment = self.get_object()

        if hasattr(shipment, 'routeleg'):
            if shipment.state == TransitState.AWAITING_PICKUP:
                # RouteTrackingData may contain data for other shipments already picked up.
                # This shipment should not include those data as it has not yet begun transit.
                tracking_data = RouteTrackingData.objects.none()
            else:
                tracking_data = RouteTrackingData.objects.filter(route__id=shipment.routeleg.route.id)
        else:
            tracking_data = TrackingData.objects.filter(shipment__id=shipment.id)

        response = Template('{"data": $geojson}')
        response = response.substitute(geojson=render_filtered_point_features(shipment, tracking_data))
        return HttpResponse(content=response, content_type='application/vnd.api+json')

    def update(self, request, *args, **kwargs):
        """
        Update the shipment with new details, overwriting the built-in method
        """
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        LOG.debug(f'Updating shipment {instance.id} with new details.')
        log_metric('transmission.info', tags={'method': 'shipments.update', 'module': __name__})

        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)

        shipment = self.perform_update(serializer)
        async_jobs = shipment.asyncjob_set.filter(state__in=[JobState.PENDING, JobState.RUNNING])
        response = self.get_serializer(shipment, serialization_type=SerializationType.RESPONSE)

        response.instance.async_job_id = async_jobs.latest('created_at').id if async_jobs else None

        return Response(response.data, status=status.HTTP_202_ACCEPTED)
