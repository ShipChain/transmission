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
from influxdb_metrics.loader import log_metric
from rest_framework import viewsets, permissions, renderers
from rest_framework.response import Response
from shipchain_common.pagination import CustomResponsePagination

from apps.permissions import ShipmentExists
from ..models import Shipment
from ..permissions import IsOwnerOrShared
from ..serializers import ChangesDiffSerializer

LOG = logging.getLogger('transmission')


class ShipmentHistoryListView(viewsets.GenericViewSet):
    http_method_names = ('get', )

    permission_classes = (
        (ShipmentExists, IsOwnerOrShared, ) if settings.PROFILES_ENABLED else (permissions.AllowAny, ShipmentExists, )
    )

    pagination_class = CustomResponsePagination

    renderer_classes = (renderers.JSONRenderer, )

    def list(self, request, *args, **kwargs):
        LOG.debug(f'Listing shipment history for shipment with id: {kwargs["shipment_pk"]}.')
        log_metric('transmission.info', tags={'method': 'shipment.history', 'module': __name__})

        shipment = Shipment.objects.get(id=kwargs['shipment_pk'])

        serializer = ChangesDiffSerializer(shipment.history.all(), request, kwargs['shipment_pk'])

        queryset = serializer.filter_queryset(serializer.historical_queryset)

        paginator = self.pagination_class()
        page = paginator.paginate_queryset(queryset, self.request, view=self)
        if page is not None:
            return paginator.get_paginated_response(serializer.get_data(page))

        return Response(serializer.get_data(queryset))
