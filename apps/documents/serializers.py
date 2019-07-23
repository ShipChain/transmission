import logging

from botocore.errorfactory import ClientError

from django.conf import settings

from enumfields.drf import EnumSupportSerializerMixin
from rest_framework_json_api import serializers
from influxdb_metrics.loader import log_metric

from apps.utils import UpperEnumField, S3PreSignedMixin
from .models import Document, DocumentType, FileType, UploadStatus
from .rpc import DocumentRPCClient

LOG = logging.getLogger('transmission')


class AbstractDocumentSerializer(S3PreSignedMixin, EnumSupportSerializerMixin, serializers.ModelSerializer):
    document_type = UpperEnumField(DocumentType, lenient=True, read_only=True, ints_as_names=True)
    file_type = UpperEnumField(FileType, lenient=True, read_only=True, ints_as_names=True)
    upload_status = UpperEnumField(UploadStatus, lenient=True, ints_as_names=True)
    presigned_s3 = serializers.SerializerMethodField()

    def __init__(self, *args, **kwargs):
        super(AbstractDocumentSerializer, self).__init__(*args, **kwargs)
        self._s3_bucket = settings.DOCUMENT_MANAGEMENT_BUCKET

    def get_presigned_s3(self, obj):
        if obj.__class__.__name__ == 'Document':
            s3_bucket = settings.S3_BUCKET
            file_extension = obj.file_type.name.lower()
        else:
            s3_bucket = settings.CSV_S3_BUCKET
            file_extension = obj.csv_file_type.name.lower()

    class Meta:
        model = Document
        if settings.PROFILES_ENABLED:
            exclude = ('owner_id',)
        read_only_fields = ('shipment',)


class ShipmentDocumentCreateSerializer(AbstractDocumentSerializer):
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
        meta_fields = ('presigned_s3', )


class ShipmentDocumentSerializer(AbstractDocumentSerializer):
    presigned_s3_thumbnail = serializers.SerializerMethodField()

    class Meta:
        model = Document
        fields = "__all__"
        if settings.PROFILES_ENABLED:
            read_only_fields = ('owner_id', 'document_type', 'file_type',)
        else:
            read_only_fields = ('document_type', 'file_type',)
        meta_fields = ('presigned_s3', 'presigned_s3_thumbnail',)

    def get_presigned_s3(self, obj):
        if obj.upload_status != UploadStatus.COMPLETE:
            return super().get_presigned_s3(obj)

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
