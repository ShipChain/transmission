import logging
from urllib.parse import unquote_plus

import re
from django.conf import settings
from django_filters import rest_framework as filters
from rest_framework import viewsets, permissions, status, mixins, exceptions
from rest_framework.response import Response
from rest_framework.views import APIView
from influxdb_metrics.loader import log_metric

from apps.authentication import DocsLambdaRequest
from .filters import DocumentFilterSet
from .models import Document
from .models import UploadStatus
from .permissions import UserHasPermission
from .tasks import get_document_from_vault
from .rpc import DocumentRPCClient
from .serializers import (DocumentSerializer,
                          DocumentCreateSerializer,
                          DocumentRetrieveSerializer, )

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

    def update(self, request, *args, **kwargs):
        """
        Update document object status according to upload status: COMPLETE or FAILED
        """
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        LOG.debug(f'Updating document {instance.id} with new details.')
        log_metric('transmission.info', tags={'method': 'documents.update', 'module': __name__})

        serializer = DocumentRetrieveSerializer(instance, data=request.data, partial=partial,
                                                context={'auth': request.auth})
        serializer.is_valid(raise_exception=True)

        self.perform_update(serializer)

        return Response(serializer.data, status=status.HTTP_200_OK)

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

        for document in queryset:
            get_document_from_vault.delay(document.id)

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = DocumentRetrieveSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = DocumentRetrieveSerializer(queryset, many=True)

        return Response(serializer.data, status=status.HTTP_202_ACCEPTED)


class S3Events(APIView):
    S3_PATH_REGEX = r'[\w]{8}(-[\w]{4}){3}-[\w]{12}\/[\w]{8}(-[\w]{4}){3}-[\w]{12}\/[\w]{8}(-[\w]{4}){3}-[\w]{12}\/' \
                    r'[\w\-_]+\.\w{3,4}'
    permission_classes = (DocsLambdaRequest,)

    def post(self, request, version, format=None):
        # Get bucket and key from PUT event
        for record in request.data['Records']:
            bucket = record['s3']['bucket']['name']
            key = unquote_plus(record['s3']['object']['key'])

            LOG.info(f'Found new object {key} in bucket {bucket}')

            if re.match(self.S3_PATH_REGEX, key):
                # Parse IDs from key, "sc_uuid/wallet_uuid/vault_uuid/document_uuid.ext"
                storage_credentials_id, wallet_uuid, vault_id, filename = key.split('/', 3)

                document_id = filename.split('.')[0]
                document = Document.objects.filter(id=document_id).first()
                if document:
                    # Save document to vault
                    DocumentRPCClient().add_document_from_s3(bucket, key, wallet_uuid,
                                                             storage_credentials_id, vault_id, filename)

                    # Update upload status
                    document.upload_status = UploadStatus.COMPLETE
                    document.save()
                else:
                    message = f'Document not found with ID {document_id}, for {key} uploaded to {bucket}'
                    LOG.warning(message)
                    raise exceptions.ParseError(detail=message)
            else:
                message = f'Document uploaded to {bucket} with key {key} does not match expected key regex'
                LOG.warning(message)
                raise exceptions.ParseError(detail=message)

        return Response(status=status.HTTP_204_NO_CONTENT)
