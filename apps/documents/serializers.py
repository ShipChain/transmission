import logging

from botocore.errorfactory import ClientError

from django.conf import settings

from enumfields.drf import EnumSupportSerializerMixin
from rest_framework_json_api import serializers
from rest_framework import exceptions, status
from influxdb_metrics.loader import log_metric

from apps.utils import UpperEnumField
from .models import Document, CsvDocument, DocumentType, FileType, CsvFileType, UploadStatus, ProcessingStatus
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
            exclude = ('owner_id',)
        read_only_fields = ('shipment',)

    def get_presigned_s3(self, obj):
        if obj.__class__.__name__ == 'Document':
            s3_bucket = settings.S3_BUCKET
            file_extension = obj.file_type.name.lower()
        else:
            s3_bucket = settings.CSV_S3_BUCKET
            file_extension = obj.csv_file_type.name.lower()

        content_type = settings.MIME_TYPE_MAP.get(file_extension)
        if not content_type:
            raise exceptions.ValidationError(f'Unsupported file type "{file_extension}"')

        pre_signed_post = settings.S3_CLIENT.generate_presigned_post(
            Bucket=s3_bucket,
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


class ShipmentDocumentCreateSerializer(DocumentSerializer):
    """
    Model serializer for documents validation for s3 signing
    """
    document_type = UpperEnumField(DocumentType, lenient=True, ints_as_names=True)
    file_type = UpperEnumField(FileType, lenient=True, ints_as_names=True)
    upload_status = UpperEnumField(UploadStatus, read_only=True, ints_as_names=True)
    presigned_s3 = serializers.SerializerMethodField()

    class Meta:
        model = Document
        if settings.PROFILES_ENABLED:
            exclude = ('owner_id',)
        read_only_fields = ('shipment',)
        meta_fields = ('presigned_s3',)

    def create(self, validated_data):
        return Document.objects.create(**validated_data, **self.context)


class ShipmentDocumentSerializer(DocumentSerializer):
    document_type = UpperEnumField(DocumentType, lenient=True, read_only=True, ints_as_names=True)
    file_type = UpperEnumField(FileType, lenient=True, read_only=True, ints_as_names=True)
    upload_status = UpperEnumField(UploadStatus, lenient=True, ints_as_names=True)
    presigned_s3 = serializers.SerializerMethodField()
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
            return None

        thumbnail_key = obj.s3_key.rsplit('.', 1)[0] + '-t.png'

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


class CsvDocumentSerializer(DocumentSerializer):
    csv_file_type = UpperEnumField(CsvFileType, lenient=True, read_only=True, ints_as_names=True)
    upload_status = UpperEnumField(UploadStatus, lenient=True, ints_as_names=True)
    processing_status = UpperEnumField(ProcessingStatus, lenient=True, ints_as_names=True)
    presigned_s3 = serializers.SerializerMethodField()

    class Meta:
        model = CsvDocument
        if settings.PROFILES_ENABLED:
            exclude = ('owner_id', 'updated_by', 'storage_credentials_id', 'shipper_wallet_id', 'carrier_wallet_id', )
        else:
            fields = '__all__'
        meta_fields = ('presigned_s3',)

    def get_presigned_s3(self, obj):
        if obj.upload_status != UploadStatus.COMPLETE:
            return super(CsvDocumentSerializer, self).get_presigned_s3(obj)
        return None


class CsvDocumentCreateSerializer(DocumentSerializer):
    csv_file_type = UpperEnumField(CsvFileType, lenient=True, ints_as_names=True)
    upload_status = UpperEnumField(UploadStatus, lenient=True, ints_as_names=True, read_only=True, required=False)
    processing_status = UpperEnumField(ProcessingStatus, lenient=True, ints_as_names=True, read_only=True,
                                       required=False)
    presigned_s3 = serializers.SerializerMethodField()

    class Meta:
        model = CsvDocument
        if settings.PROFILES_ENABLED:
            exclude = ('owner_id', 'updated_by', )
        else:
            fields = '__all__'

        meta_fields = ('presigned_s3', )

    def validate_shipper_wallet_id(self, shipper_wallet_id):
        if settings.PROFILES_ENABLED:
            response = settings.REQUESTS_SESSION.get(f'{settings.PROFILES_URL}/api/v1/wallet/{shipper_wallet_id}/',
                                                     headers={'Authorization': 'JWT {}'.format(self.context['auth'])})

            if response.status_code != status.HTTP_200_OK:
                raise serializers.ValidationError('User does not have access to this wallet in ShipChain Profiles')

        return shipper_wallet_id

    def validate_storage_credentials_id(self, storage_credentials_id):
        if settings.PROFILES_ENABLED:
            response = settings.REQUESTS_SESSION.get(
                f'{settings.PROFILES_URL}/api/v1/storage_credentials/{storage_credentials_id}/',
                headers={'Authorization': 'JWT {}'.format(self.context['auth'])})

            if response.status_code != status.HTTP_200_OK:
                raise serializers.ValidationError(
                    'User does not have access to this storage credential in ShipChain Profiles')

        return storage_credentials_id


class CsvDocumentCreateResponseSerializer(CsvDocumentCreateSerializer):
    class Meta:
        model = CsvDocument
        if settings.PROFILES_ENABLED:
            exclude = ('owner_id', 'updated_by', 'storage_credentials_id', 'shipper_wallet_id', 'carrier_wallet_id', )
        else:
            fields = '__all__'

        meta_fields = ('presigned_s3', )
