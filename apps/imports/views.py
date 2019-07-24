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
from django_filters import rest_framework as filters
from rest_framework import viewsets, permissions, status, mixins
from rest_framework.response import Response
from influxdb_metrics.loader import log_metric

from apps.authentication import get_jwt_from_request
from apps.permissions import IsOwner, get_owner_id, owner_access_filter
from .filters import ShipmentImportFilterSet
from .models import ShipmentImport
from .serializers import ShipmentImportSerializer, ShipmentImportCreateSerializer

LOG = logging.getLogger('transmission')


class ShipmentImportsViewSet(mixins.CreateModelMixin,
                             mixins.RetrieveModelMixin,
                             mixins.UpdateModelMixin,
                             mixins.ListModelMixin,
                             viewsets.GenericViewSet):

    queryset = ShipmentImport.objects.all()
    serializer_class = ShipmentImportSerializer
    permission_classes = ((permissions.IsAuthenticated, IsOwner, ) if settings.PROFILES_ENABLED
                          else (permissions.AllowAny, ))
    filter_backends = (filters.DjangoFilterBackend, )
    filter_class = ShipmentImportFilterSet

    def get_queryset(self):
        return self.queryset.filter(owner_access_filter(self.request))

    def perform_create(self, serializer):
        if settings.PROFILES_ENABLED:
            created = serializer.save(owner_id=get_owner_id(self.request), masquerade_id=self.request.user.id)
        else:
            created = serializer.save()
        return created

    def create(self, request, *args, **kwargs):
        """
        Create a pre-signed s3 post and create a corresponding document object with pending status
        """
        LOG.debug(f'Creating a ShipmentImport document object')
        log_metric('transmission.info', tags={'method': 'imports.create', 'module': __name__})

        serializer = ShipmentImportCreateSerializer(data=request.data, context={'auth': get_jwt_from_request(request)})
        serializer.is_valid(raise_exception=True)
        doc_obj = self.perform_create(serializer)

        return Response(self.get_serializer(doc_obj).data, status=status.HTTP_201_CREATED)
