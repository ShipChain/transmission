import logging

from botocore.errorfactory import ClientError

from django.conf import settings

from enumfields.drf import EnumSupportSerializerMixin
from rest_framework_json_api import serializers
from influxdb_metrics.loader import log_metric

from apps.utils import UpperEnumField
from .models import Document, DocumentType, FileType, UploadStatus, IMAGE_TYPES
from .rpc import DocumentRPCClient

LOG = logging.getLogger('transmission')


class DocumentSerializer(EnumSupportSerializerMixin, serializers.ModelSerializer):
    document_type = UpperEnumField(DocumentType, lenient=True, read_only=True, ints_as_names=True)
    file_type = UpperEnumField(FileType, lenient=True, read_only=True, ints_as_names=True)
    upload_status = UpperEnumField(UploadStatus, lenient=True, ints_as_names=True)
    presigned_s3 = serializers.SerializerMethodField()

    class Meta:
        model = Document
        if settings.PROFILES_ENABLED:
            exclude = ('owner_id', 'shipment',)
        else:
            exclude = ('shipment',)

    def get_presigned_s3(self, obj):
        file_extension = obj.file_type.name.lower()

        if file_extension in IMAGE_TYPES:
            content_type = f"image/{file_extension}"
        else:
            content_type = f"application/{file_extension}"

        pre_signed_post = settings.S3_CLIENT.generate_presigned_post(
            Bucket=settings.S3_BUCKET,
            Key=obj.s3_key,
            Fields={"acl": "private", "Content-Type": content_type},
            Conditions=[
                {"acl": "private"},
                {"Content-Type": content_type},
                ["content-length-range", 0, settings.S3_MAX_BYTES]
            ],
            ExpiresIn=settings.S3_URL_LIFE
        )

        return pre_signed_post


class DocumentCreateSerializer(DocumentSerializer):
    """
    Model serializer for documents validation for s3 signing
    """
    document_type = UpperEnumField(DocumentType, lenient=True, ints_as_names=True)
    file_type = UpperEnumField(FileType, lenient=True, ints_as_names=True)
    upload_status = UpperEnumField(UploadStatus, read_only=True, ints_as_names=True)
    shipment_id = serializers.CharField(max_length=36)

    class Meta:
        model = Document
        if settings.PROFILES_ENABLED:
            exclude = ('owner_id', 'shipment',)
        else:
            exclude = ('shipment',)
        meta_fields = ('presigned_s3',)


class DocumentRetrieveSerializer(DocumentSerializer):
    presigned_s3_thumbnail = serializers.SerializerMethodField()

    class Meta:
        model = Document
        exclude = ('shipment',)
        if settings.PROFILES_ENABLED:
            read_only_fields = ('owner_id', 'document_type', 'file_type',)
        else:
            read_only_fields = ('document_type', 'file_type',)
        meta_fields = ('presigned_s3', 'presigned_s3_thumbnail',)

    def get_presigned_s3(self, obj):
        if obj.upload_status != UploadStatus.COMPLETE:
            return super().get_presigned_s3(obj)

        try:
            settings.S3_CLIENT.head_object(Bucket=settings.S3_BUCKET, Key=obj.s3_key)
        except ClientError:
            # The document doesn't exist anymore in the bucket. The bucket is going to be repopulated from vault
            result = DocumentRPCClient().put_document_in_s3(settings.S3_BUCKET, obj.s3_key, obj.shipper_wallet_id,
                                                            obj.storage_id, obj.vault_id, obj.filename)
            if not result:
                return None

        url = settings.S3_CLIENT.generate_presigned_url(
            'get_object',
            Params={
                'Bucket': f"{settings.S3_BUCKET}",
                'Key': obj.s3_key
            },
            ExpiresIn=settings.S3_URL_LIFE
        )

        LOG.debug(f'Generated one time s3 url for: {obj.id}')
        log_metric('transmission.info', tags={'method': 'documents.generate_presigned_url', 'module': __name__})

        return url

    def get_presigned_s3_thumbnail(self, obj):
        if obj.upload_status != UploadStatus.COMPLETE:
            return super().get_presigned_s3(obj)

        thumbnail_key = obj.s3_key[:-4] + '-t.' + obj.file_type.name.lower()

        url = settings.S3_CLIENT.generate_presigned_url(
            'get_object',
            Params={
                'Bucket': f"{settings.S3_BUCKET}",
                'Key': thumbnail_key
            },
            ExpiresIn=settings.S3_URL_LIFE
        )

        LOG.debug(f'Generated one time s3 url thumbnail for: {obj.id}')
        log_metric('transmission.info', tags={'method': 'documents.generate_presigned_s3_thumbnail',
                                              'module': __name__})

        return url
