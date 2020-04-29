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

from django.db.models.aggregates import Avg, Count, Max, Min, StdDev, Sum, Variance
from django.db.models import Window, RowRange, F, ValueRange, functions, IntegerField
from django.conf import settings
from django.utils.decorators import method_decorator
from django_filters.rest_framework import DjangoFilterBackend
from fancy_cache import cache_page
from rest_framework import permissions, filters, mixins, viewsets
from rest_framework.exceptions import ValidationError
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response

from apps.permissions import ShipmentExists
from apps.utils import Aggregates
from ..filters import TelemetryFilter
from ..models import Shipment, TelemetryData
from ..permissions import IsOwnerOrShared
from ..serializers import TelemetryResponseSerializer


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

    def _aggregrate_queryset(self, queryset, aggregate):
        if aggregate not in Aggregates.__members__:
            raise ValidationError(f'Invalid aggregrate supplied should be in: {Aggregates.__members__}')

        method = Aggregates[aggregate].value

        queryset = queryset.annotate(
            avg_telemetry=Window(
                # expression=method('value'),
                expression=Avg('value'),
                partition_by=[F('sensor_id'),
                              functions.TruncHour('timestamp'),
                              functions.Cast(functions.ExtractMinute('timestamp') / 5, IntegerField())
                              ],
                order_by=F('timestamp').desc(),
                # partition_by=[F('sensor_id')]
            )
        )

        return queryset

    def get_queryset(self):
        shipment = Shipment.objects.get(pk=self.kwargs['shipment_pk'])

        begin = (shipment.pickup_act or datetime.min).replace(tzinfo=timezone.utc)
        end = (shipment.delivery_act or datetime.max).replace(tzinfo=timezone.utc)

        return self.queryset.filter(shipment=shipment, timestamp__range=(begin, end))

    # @method_decorator(cache_page(60 * 60, remember_all_urls=True))  # Cache responses for 1 hour
    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())

        aggregate = request.query_params.get('aggregate', None)
        print(request.query_params)
        print(f'Aggregrate: {aggregate}')

        if aggregate:
            queryset = self._aggregrate_queryset(queryset, aggregate, )

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)
