import logging

from django.conf import settings
from django_filters import rest_framework as filters
from rest_framework import viewsets, permissions, status, mixins
from rest_framework.response import Response
from rest_framework.decorators import action
from influxdb_metrics.loader import log_metric

from .permissions import UserHasPermission

from .serializers import (DocumentSerializer,
                          DocumentCreateSerializer,
                          DocumentRetrieveSerializer,)
from .models import Document
from .filters import DocumentFilterSet


LOG = logging.getLogger('transmission')


class DocumentViewSet(mixins.CreateModelMixin,
                      mixins.RetrieveModelMixin,
                      mixins.ListModelMixin,
                      mixins.UpdateModelMixin,
                      viewsets.GenericViewSet):
    queryset = Document.objects.all()
    serializer_class = DocumentSerializer
    permission_classes = (permissions.IsAuthenticated, UserHasPermission,)
    filter_backends = (filters.DjangoFilterBackend,)
    filter_class = DocumentFilterSet

    def get_queryset(self):
        queryset = self.queryset
        if settings.PROFILES_ENABLED:
            queryset = queryset.filter(owner_id=self.request.user.id)
        return queryset

    def perform_create(self, serializer):
        if settings.PROFILES_ENABLED:
            created = serializer.save(owner_id=self.request.user.id)
        else:
            created = serializer.save()
        return created

    def create(self, request, *args, **kwargs):
        """
        Create a pre-signed s3 post and create a corresponding pdf document object with pending status
        """
        LOG.debug(f'Creating a document object.')
        log_metric('transmission.info', tags={'method': 'documents.create', 'module': __name__})

        serializer = DocumentCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = DocumentRetrieveSerializer(instance)
        return Response(serializer.data)

    def list(self, request, *args, **kwargs):
        if 'shipment_pk' in kwargs.keys():
            documents = Document.objects.filter(shipment__id=kwargs['shipment_pk']).order_by('updated_at')
            queryset = self.filter_queryset(documents)
        else:
            queryset = self.filter_queryset(self.get_queryset())

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = DocumentRetrieveSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = DocumentRetrieveSerializer(queryset, many=True)

        return Response(serializer.data, status=status.HTTP_202_ACCEPTED)
