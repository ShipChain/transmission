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
from apps.utils import Aggregates, TimeTrunc
from ..filters import TelemetryFilter
from ..models import Shipment, TelemetryData
from ..permissions import IsOwnerOrShared
from ..serializers import TelemetryResponseSerializer, TelemetryResponseAggregrateSerializer


class TelemetryViewSet(mixins.ListModelMixin,
                       viewsets.GenericViewSet):

    queryset = TelemetryData.objects.all()

    serializer_class = TelemetryResponseSerializer

    permission_classes = (
        (ShipmentExists, IsOwnerOrShared) if settings.PROFILES_ENABLED
        else (permissions.AllowAny, ShipmentExists, )
    )

    filter_backends = (filters.OrderingFilter, DjangoFilterBackend, )

    filterset_class = TelemetryFilter

    renderer_classes = (JSONRenderer,)

    def _truncate_time(self):
        segment = self.request.query_params.get('per')
        if not segment:
            raise ValidationError(f'No time selector supplied with aggregation. '
                                  f'Should be in {list(TimeTrunc.__members__.keys())}')
        if segment not in TimeTrunc.__members__:
            raise ValidationError(f'Invalid time selector supplied, should be in: {list(TimeTrunc.__members__.keys())}')

        return TimeTrunc[segment].value('timestamp')

    def _aggregrate_queryset(self, queryset, aggregate):
        if aggregate not in Aggregates.__members__:
            raise ValidationError(f'Invalid aggregrate supplied should be in: {list(Aggregates.__members__.keys())}')

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

        return self.queryset.filter(shipment=shipment, timestamp__range=(begin, end))

    @method_decorator(cache_page(60 * 60, remember_all_urls=True))  # Cache responses for 1 hour
    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        before = request.query_params.get('before')
        after = request.query_params.get('after')
        if before and after and (dateutil.parser.parse(before) > dateutil.parser.parse(after)):
            raise ValidationError(
                f'Invalid timemismatch applied. Before timestamp {before} is greater than after: {after}')

        aggregate = request.query_params.get('aggregate', None)

        if aggregate:
            queryset = self._aggregrate_queryset(queryset, aggregate, )
            self.serializer_class = TelemetryResponseAggregrateSerializer
        else:
            if request.query_params.get('per'):
                raise ValidationError(f'No aggregrator supplied with time selector. '
                                      f'Should be in {list(Aggregates.__members__.keys())}')

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)
