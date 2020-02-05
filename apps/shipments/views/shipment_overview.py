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

from django.db.models import Max
from django_filters.rest_framework import DjangoFilterBackend
from influxdb_metrics.loader import log_metric
from rest_framework import filters, permissions, status
from rest_framework.generics import ListAPIView
from rest_framework.response import Response
from rest_framework_gis.filters import InBBoxFilter

from apps.permissions import get_owner_id
from ..serializers import DevicesQueryParamsSerializer, ShipmentLocationSerializer
from ..models import Shipment, TrackingData
from ..filters import ShipmentFilter, SHIPMENT_SEARCH_FIELDS

LOG = logging.getLogger('transmission')


class ShipmentOverviewListView(ListAPIView):

    permission_classes = (permissions.IsAuthenticated, )

    serializer_class = ShipmentLocationSerializer

    filter_backends = (filters.SearchFilter, filters.OrderingFilter, DjangoFilterBackend,)

    filterset_class = ShipmentFilter

    ordering_fields = ('created_at', )

    search_fields = SHIPMENT_SEARCH_FIELDS

    bbox_filter_field = 'point'

    queryset = TrackingData.objects.filter(shipment__device_id__isnull=False)
    shipment_queryset = Shipment.objects.filter(device_id__isnull=False)

    def filter_tracking_data_queryset(self, owner_id, queryset):

        # Shipment owner filter
        shipment_queryset = self.shipment_queryset.filter(owner_id=owner_id)

        # Shipment fields filter
        shipment_queryset = self.filter_queryset(shipment_queryset)

        latest_tracking = shipment_queryset.annotate(
            latest_tracking_created=Max('trackingdata__created_at')
        ).values_list('latest_tracking_created')

        tracking_data_queryset = queryset.filter(shipment__in=shipment_queryset,
                                                 created_at__in=latest_tracking)

        # The Bbox filter needs to happen here for performance reasons.
        # tracking_data_queryset at this level contains significantly
        # less points than if performed with the view filter_queryset
        bbox_tracking_data_queryset = InBBoxFilter().filter_queryset(self.request, tracking_data_queryset, self)

        return bbox_tracking_data_queryset

    def get(self, request, *args, **kwargs):
        owner_id = get_owner_id(request)

        LOG.debug(f'Listing shipment with device for [{owner_id}]')
        log_metric('transmission.info', tags={'method': 'devices.list', 'module': __name__})

        param_serializer = DevicesQueryParamsSerializer(data=request.query_params)
        param_serializer.is_valid(raise_exception=True)

        queryset = self.filter_tracking_data_queryset(owner_id, self.queryset)

        paginator = self.pagination_class()
        page = paginator.paginate_queryset(queryset, request, view=self)

        if page is not None:

            serializer = self.serializer_class(page, many=True)
            return paginator.get_paginated_response(serializer.data)

        serializer = self.serializer_class(queryset, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)
