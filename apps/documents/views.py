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
from urllib.parse import unquote_plus

import re
from django.conf import settings
from django_filters import rest_framework as filters
from rest_framework import viewsets, permissions, status, mixins, exceptions
from rest_framework.response import Response
from rest_framework.views import APIView
from influxdb_metrics.loader import log_metric

from apps.authentication import DocsLambdaRequest
from apps.jobs.models import AsyncActionType
from apps.permissions import get_owner_id, UserHasShipmentPermission
from apps.utils import UploadStatus
from .filters import DocumentFilterSet
from .models import Document
from .rpc import DocumentRPCClient
from .serializers import DocumentSerializer, DocumentCreateSerializer

LOG = logging.getLogger('transmission')


class DocumentViewSet(mixins.CreateModelMixin,
                      mixins.RetrieveModelMixin,
                      mixins.UpdateModelMixin,
                      mixins.ListModelMixin,
                      viewsets.GenericViewSet):
    queryset = Document.objects.all()
    serializer_class = DocumentSerializer
    permission_classes = ((UserHasShipmentPermission, ) if settings.PROFILES_ENABLED else (permissions.AllowAny, ))
    filter_backends = (filters.DjangoFilterBackend,)
    filter_class = DocumentFilterSet

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
        LOG.debug(f'Creating a document object.')
        log_metric('transmission.info', tags={'method': 'documents.create', 'module': __name__})

        serializer = DocumentCreateSerializer(data=request.data, context={'shipment_id': self.kwargs['shipment_pk']})
        serializer.is_valid(raise_exception=True)
        doc_obj = self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return Response(self.get_serializer(doc_obj).data, status=status.HTTP_201_CREATED, headers=headers)

    def update(self, request, *args, **kwargs):
        """
        Update document object status according to upload status: COMPLETE or FAILED
        """
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        LOG.debug(f'Updating document {instance.id} with new details.')
        log_metric('transmission.info', tags={'method': 'documents.update', 'module': __name__})

        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)

        self.perform_update(serializer)

        return Response(serializer.data, status=status.HTTP_200_OK)


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
                key_fields = dict()
                key_fields['storage_credentials_id'], \
                    key_fields['wallet_uuid'], \
                    key_fields['vault_id'], \
                    key_fields['filename'] = key.split('/', 3)

                document_id = key_fields['filename'].split('.')[0]
                document = Document.objects.filter(id=document_id).first()
                if document:
                    # Save document to vault
                    signature = DocumentRPCClient().add_document_from_s3(bucket, key,
                                                                         key_fields['wallet_uuid'],
                                                                         key_fields['storage_credentials_id'],
                                                                         key_fields['vault_id'],
                                                                         key_fields['filename'])

                    # Update upload status
                    document.upload_status = UploadStatus.COMPLETE
                    document.save()
                    document.shipment.set_vault_hash(signature['hash'], action_type=AsyncActionType.DOCUMENT)
                else:
                    message = f'Document not found with ID {document_id}, for {key} uploaded to {bucket}'
                    LOG.warning(message)
                    raise exceptions.ParseError(detail=message)
            else:
                message = f'Document uploaded to {bucket} with key {key} does not match expected key regex'
                LOG.warning(message)
                raise exceptions.ParseError(detail=message)

        return Response(status=status.HTTP_204_NO_CONTENT)
