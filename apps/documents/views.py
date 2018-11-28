import logging

from django.conf import settings
from django_filters import rest_framework as filters
from rest_framework import viewsets, permissions, status
from rest_framework.response import Response
from influxdb_metrics.loader import log_metric

from .permissions import UserHasPermission

from .serializers import (DocumentSerializer,
                          DocumentCreateSerializer,
                          DocumentUpdateSerializer,
                          DocumentRetrieveSerializer,)
from .models import Document
from .utils import DocumentsPagination, DocumentFilterSet


LOG = logging.getLogger('transmission')


class DocumentViewSet(viewsets.ModelViewSet):
    queryset = Document.objects.all()
    serializer_class = DocumentSerializer
    permission_classes = (permissions.IsAuthenticated, UserHasPermission,)
    pagination_class = DocumentsPagination
    filter_backends = (filters.DjangoFilterBackend,)
    filter_class = DocumentFilterSet
    http_method_names = ['get', 'post', 'put']

    def get_queryset(self):
        queryset = self.queryset
        if settings.PROFILES_URL:
            queryset = queryset.filter(owner_id=self.request.user.id)
        return queryset

    def perform_create(self, serializer):
        if settings.PROFILES_URL:
            created = serializer.save(owner_id=self.request.user.id)
        else:
            created = serializer.save()
        return created

    def perform_update(self, serializer):
        return serializer.save()

    def create(self, request, *args, **kwargs):
        """
        Create a pre-signed s3 post and create a corresponding pdf document object with pending status
        """
        LOG.debug(f'Creating a document object.')
        log_metric('transmission.info', tags={'method': 'documents.create', 'module': __name__})

        serializer = DocumentCreateSerializer(data=request.data, context={'auth': request.auth})
        serializer.is_valid(raise_exception=True)

        # Create document object
        document = self.perform_create(serializer)
        presigned_data = serializer.s3_sign(document=document)

        # Assign s3 path
        document.assign_s3_path(path=presigned_data['uri'])

        return Response(presigned_data, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        """
        Update document object status according to upload status: COMPLETED or FAILED
        """
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        LOG.debug(f'Updating document {instance} with new details.')
        log_metric('transmission.info', tags={'method': 'documents.update', 'module': __name__})

        serializer = DocumentUpdateSerializer(instance, data=request.data, partial=partial,
                                              context={'auth': request.auth})
        serializer.is_valid(raise_exception=True)

        document = self.perform_update(serializer)

        response = DocumentSerializer(document)

        return Response(response.data, status=status.HTTP_202_ACCEPTED)

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = DocumentRetrieveSerializer(instance)
        serializer.validate_upload_status()

        return Response(serializer.data, status=status.HTTP_202_ACCEPTED)

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = DocumentRetrieveSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = DocumentRetrieveSerializer(queryset, many=True)

        return Response(serializer.data, status=status.HTTP_202_ACCEPTED)
