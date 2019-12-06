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

from apps.permissions import get_owner_id, UserHasShipmentPermission

from .models import ShipmentNote
from .serializers import ShipmentNoteSerializer

LOG = logging.getLogger('transmission')


class ShipmentNoteViewSet(mixins.CreateModelMixin,
                          mixins.RetrieveModelMixin,
                          mixins.ListModelMixin,
                          viewsets.GenericViewSet):
    queryset = ShipmentNote.objects.all()
    serializer_class = ShipmentNoteSerializer
    permission_classes = ((UserHasShipmentPermission, ) if settings.PROFILES_ENABLED else (permissions.AllowAny, ))
    filter_backends = (filters.DjangoFilterBackend,)
    # filter_class = DocumentFilterSet

    def get_queryset(self):
        return self.queryset.filter(shipment__id=self.kwargs['shipment_pk'])

    def perform_create(self, serializer):
        if settings.PROFILES_ENABLED:
            created = serializer.save(owner_id=get_owner_id(self.request), shipment_id=self.kwargs['shipment_pk'])
        else:
            created = serializer.save()
        return created

    def create(self, request, *args, **kwargs):
        """
        Create a pre-signed s3 post and create a corresponding pdf document object with pending status
        """
        LOG.debug(f'Creating a ShipmentNote object.')
        log_metric('transmission.info', tags={'method': 'notes.create', 'module': __name__})

        serializer = self.serializer_class(data=request.data, context={'shipment_id': self.kwargs['shipment_pk']})
        serializer.is_valid(raise_exception=True)
        note_object = self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return Response(self.get_serializer(note_object).data, status=status.HTTP_201_CREATED, headers=headers)
