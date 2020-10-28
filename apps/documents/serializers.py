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

from botocore.errorfactory import ClientError

from django.conf import settings

from enumfields.drf import EnumSupportSerializerMixin
from rest_framework_json_api import serializers
from influxdb_metrics.loader import log_metric
from shipchain_common.exceptions import AccountLimitReached
from shipchain_common.utils import UpperEnumField

from apps.utils import S3PreSignedMixin
from .models import Document, DocumentType, FileType, UploadStatus
from .rpc import DocumentRPCClient

LOG = logging.getLogger('transmission')


class BaseDocumentSerializer(S3PreSignedMixin, EnumSupportSerializerMixin, serializers.ModelSerializer):
    document_type = UpperEnumField(DocumentType, lenient=True, read_only=True, ints_as_names=True)
    file_type = UpperEnumField(FileType, lenient=True, read_only=True, ints_as_names=True)
    upload_status = UpperEnumField(UploadStatus, lenient=True, ints_as_names=True)
    presigned_s3 = serializers.SerializerMethodField()
    _s3_bucket = settings.DOCUMENT_MANAGEMENT_BUCKET


class DocumentCreateSerializer(BaseDocumentSerializer):
    """
    Model serializer for documents validation for s3 signing
    """
    document_type = UpperEnumField(DocumentType, lenient=True, ints_as_names=True)
    file_type = UpperEnumField(FileType, lenient=True, ints_as_names=True)
    upload_status = UpperEnumField(UploadStatus, read_only=True, ints_as_names=True)

    class Meta:
        model = Document
        if settings.PROFILES_ENABLED:
            exclude = ('owner_id', 'shipment', )
        else:
            exclude = ('shipment', )
        meta_fields = ('presigned_s3', )

    def create(self, validated_data):
        validated_data['shipment_id'] = self.context['view'].kwargs['shipment_pk']

        if settings.PROFILES_ENABLED:
            # Enforce account limits
            document_limit = self.context['request'].user.get_limit('shipments', 'documents')
            if document_limit:
                shipment_document_count = Document.objects.filter(shipment_id=validated_data['shipment_id']).count()
                if shipment_document_count + 1 > document_limit:
                    raise AccountLimitReached()

        return super().create(validated_data)


class DocumentSerializer(BaseDocumentSerializer):
    presigned_s3_thumbnail = serializers.SerializerMethodField()

    class Meta:
        model = Document
        fields = "__all__"
        if settings.PROFILES_ENABLED:
            read_only_fields = ('owner_id', 'document_type', 'file_type',)
        else:
            read_only_fields = ('document_type', 'file_type',)
        meta_fields = ('presigned_s3', 'presigned_s3_thumbnail',)

    def get_presigned_s3(self, obj):  # pylint:disable=arguments-differ
        if obj.upload_status != UploadStatus.COMPLETE:
            file_size_limit = None
            if settings.PROFILES_ENABLED:
                # Enforce account limits
                file_size_limit = self.context['request'].user.get_limit('documents', 'size_mb')
            return super().get_presigned_s3(obj, file_size_limit)

        try:
            settings.S3_CLIENT.head_object(Bucket=self._s3_bucket, Key=obj.s3_key)
        except ClientError:
            # The document doesn't exist anymore in the bucket. The bucket is going to be repopulated from vault
            result = DocumentRPCClient().put_document_in_s3(self._s3_bucket, obj.s3_key, obj.shipper_wallet_id,
                                                            obj.storage_id, obj.vault_id, obj.filename)
            if not result:
                return None

        url = settings.S3_CLIENT.generate_presigned_url(
            'get_object',
            Params={
                'Bucket': f"{self._s3_bucket}",
                'Key': obj.s3_key
            },
            ExpiresIn=settings.S3_URL_LIFE
        )

        LOG.debug(f'Generated one time s3 url for: {obj.id}')
        log_metric('transmission.info', tags={'method': 'documents.generate_presigned_url', 'module': __name__})

        return url

    def get_presigned_s3_thumbnail(self, obj):
        if obj.upload_status != UploadStatus.COMPLETE:
            return None

        thumbnail_key = obj.s3_key.rsplit('.', 1)[0] + '-t.png'

        url = settings.S3_CLIENT.generate_presigned_url(
            'get_object',
            Params={
                'Bucket': f"{self._s3_bucket}",
                'Key': thumbnail_key
            },
            ExpiresIn=settings.S3_URL_LIFE
        )

        LOG.debug(f'Generated one time s3 url thumbnail for: {obj.id}')
        log_metric('transmission.info', tags={'method': 'documents.generate_presigned_s3_thumbnail',
                                              'module': __name__})

        return url
