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
from django.db.models import Max, OuterRef, Subquery
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, permissions
from rest_framework.generics import ListAPIView
from rest_framework_gis.filters import InBBoxFilter
from rest_framework_json_api import views as jsapi_views

from apps.permissions import get_owner_id
from ..serializers import QueryParamsSerializer, TrackingOverviewSerializer
from ..models import TrackingData
from ..filters import ShipmentOverviewFilter, SHIPMENT_SEARCH_FIELDS

LOG = logging.getLogger('transmission')


class ShipmentOverviewListView(jsapi_views.PreloadIncludesMixin,
                               jsapi_views.AutoPrefetchMixin,
                               jsapi_views.RelatedMixin,
                               ListAPIView):
    queryset = TrackingData.objects.all()

    serializer_class = TrackingOverviewSerializer
    permission_classes = (permissions.IsAuthenticated,)

    filter_backends = (InBBoxFilter, filters.SearchFilter, filters.OrderingFilter, DjangoFilterBackend,)
    bbox_filter_field = 'point'
    search_fields = tuple([f'shipment__{field}' for field in SHIPMENT_SEARCH_FIELDS])
    ordering_fields = ('shipment__created_at', )
    filterset_class = ShipmentOverviewFilter

    def dispatch(self, request, *args, **kwargs):
        # pylint:disable=protected-access
        request.GET._mutable = True  # Make query_params mutable
        for param in dict(request.GET):
            # Prepend non-trackingdata search/filter/order query params with 'shipment__' to properly query relation
            if param not in ('search', 'in_bbox',) and request.GET.getlist(param):
                request.GET.setlist(f'shipment__{param}', request.GET.pop(param))
        request.GET._mutable = False  # Make query_params immutable
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self, *args, **kwargs):
        queryset = super().get_queryset(*args, **kwargs)

        # Get latest tracking point for each shipment
        # Borrowed subquery example from https://stackoverflow.com/a/43926433
        queryset = queryset.filter(id=Subquery(
            TrackingData.objects.filter(shipment=OuterRef('shipment'))
            .values('shipment').annotate(latest_tracking=Max('created_at')).values('id')[:1]
        ))

        if settings.PROFILES_ENABLED:
            # Filter by owner
            queryset.filter(shipment__owner_id=get_owner_id(self.request))

        return queryset

    def get(self, request, *args, **kwargs):
        # Validate query parameters with a request serializer
        param_serializer = QueryParamsSerializer(data=request.query_params)
        param_serializer.is_valid(raise_exception=True)

        return super().get(request, *args, **kwargs)
