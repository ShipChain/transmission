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
from datetime import datetime, timezone

import dateutil.parser
from django.conf import settings
from django.utils.decorators import method_decorator
from django_filters.rest_framework import DjangoFilterBackend
from fancy_cache import cache_page
from rest_framework import permissions, filters, mixins, viewsets
from rest_framework.exceptions import ValidationError
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response

from apps.permissions import ShipmentExists
from apps.routes.models import RouteTelemetryData
from apps.routes.serializers import RouteTelemetryResponseSerializer, RouteTelemetryResponseAggregateSerializer
from apps.shipments.filters import TelemetryFilter, RouteTelemetryFilter
from apps.shipments.models import Shipment, TelemetryData, TransitState, AccessRequest, Endpoints, PermissionLevel
from apps.shipments.permissions import IsOwnerOrShared
from apps.shipments.serializers import TelemetryResponseSerializer, TelemetryResponseAggregateSerializer
from apps.utils import Aggregates, TimeTrunc


class TelemetryViewSet(mixins.ListModelMixin,
                       viewsets.GenericViewSet):

    permission_classes = (
        (ShipmentExists, IsOwnerOrShared | AccessRequest.permission(Endpoints.shipment, PermissionLevel.READ_ONLY),
         ) if settings.PROFILES_ENABLED
        else (permissions.AllowAny, ShipmentExists, )
    )

    filter_backends = (filters.OrderingFilter, DjangoFilterBackend, )

    filterset_class = TelemetryFilter

    renderer_classes = (JSONRenderer,)

    def _validate_query_parameters(self):
        segment = self.request.query_params.get('per', None)
        aggregate = self.request.query_params.get('aggregate', None)
        before = self.request.query_params.get('before', None)
        after = self.request.query_params.get('after', None)

        if aggregate and aggregate not in Aggregates.__members__:
            raise ValidationError(f'Invalid aggregate supplied should be in: {list(Aggregates.__members__.keys())}')

        if segment and segment not in TimeTrunc.__members__:
            raise ValidationError(f'Invalid time selector supplied, should be in: {list(TimeTrunc.__members__.keys())}')

        if not aggregate and segment:
            raise ValidationError(f'No aggregator supplied with time selector. '
                                  f'Should be in {list(Aggregates.__members__.keys())}')

        if aggregate and not segment:
            raise ValidationError(f'No time selector supplied with aggregation. '
                                  f'Should be in {list(TimeTrunc.__members__.keys())}')

        if before and after and (dateutil.parser.parse(before) > dateutil.parser.parse(after)):
            raise ValidationError(f'Invalid timemismatch applied. '
                                  f'Before timestamp {before} is greater than after: {after}')

    def _truncate_time(self):
        segment = self.request.query_params.get('per')
        return TimeTrunc[segment].value('timestamp')

    def _aggregate_queryset(self, queryset):
        aggregate = self.request.query_params.get('aggregate', None)

        if not aggregate:
            return queryset

        method = Aggregates[aggregate].value

        queryset = queryset.annotate(
            window=self._truncate_time()  # Adds a column 'window' that is a truncated timestamp
        ).values(
            'sensor_id', 'hardware_id', 'window'  # Adds a GROUP BY for sensor_id/hardware_id/window
        ).annotate(
            aggregate_value=method('value')  # Calls aggregation function for sensor_id/window group
        ).order_by('window')  # Clears default ordering, see:
        # https://docs.djangoproject.com/en/2.2/topics/db/aggregation/#interaction-with-default-ordering-or-order-by

        return queryset

    def get_queryset(self):
        shipment = Shipment.objects.get(pk=self.kwargs['shipment_pk'])

        begin = (shipment.pickup_act or datetime.min).replace(tzinfo=timezone.utc)
        end = (shipment.delivery_act or datetime.max).replace(tzinfo=timezone.utc)

        if hasattr(shipment, 'routeleg'):
            if shipment.state == TransitState.AWAITING_PICKUP:
                # RouteTelemetryData may contain data for other shipments already picked up.
                # This shipment should not include those data as it has not yet begun transit.
                queryset = RouteTelemetryData.objects.none()
            else:
                queryset = RouteTelemetryData.objects.filter(route__id=shipment.routeleg.route.id)
            self.filterset_class = RouteTelemetryFilter
        else:
            queryset = TelemetryData.objects.filter(shipment__id=shipment.id)

        return queryset.filter(timestamp__range=(begin, end))

    def get_serializer_class(self):
        shipment = Shipment.objects.get(pk=self.kwargs['shipment_pk'])
        aggregate = self.request.query_params.get('aggregate', None)

        if hasattr(shipment, 'routeleg'):
            return RouteTelemetryResponseAggregateSerializer if aggregate else RouteTelemetryResponseSerializer

        return TelemetryResponseAggregateSerializer if aggregate else TelemetryResponseSerializer

    @method_decorator(cache_page(60 * 60, remember_all_urls=True))  # Cache responses for 1 hour
    def list(self, request, *args, **kwargs):
        self._validate_query_parameters()

        queryset = self.filter_queryset(self.get_queryset())
        queryset = self._aggregate_queryset(queryset)

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)
