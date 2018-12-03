from django.conf import settings

from enumfields.drf import EnumField
from rest_framework_json_api import serializers

from apps.utils import get_s3_client
from .models import Document, DocumentType, FileType, UploadStatus


class DocumentCreateSerializer(serializers.ModelSerializer):
    """
    Model serializer for documents validation for s3 signing
    """
    document_type = EnumField(DocumentType, ints_as_names=True)
    file_type = EnumField(FileType, ints_as_names=True)
    shipment_id = serializers.CharField(max_length=36)

    class Meta:
        model = Document
        fields = ['name', 'description', 'document_type', 'file_type', 'size', 'shipment_id']

    def s3_sign(self, document=None):
        data = self.validated_data
        s_3, _ = get_s3_client()
        bucket = settings.S3_BUCKET
        file_type = data['file_type']
        file_type_name = file_type.name.lower()

        # Allowed files type list
        img_types_list = [enum.name.lower() for enum in FileType]
        img_types_list.pop(img_types_list.index('pdf'))

        if file_type_name in img_types_list:
            content_type = f"image/{file_type_name}"
        else:
            content_type = f"application/{file_type_name}"

        shipment = document.shipment
        file_s3_path = f"{shipment.storage_credentials_id}/{shipment.shipper_wallet_id}/{shipment.vault_id}/" \
            f"{document.id}.{file_type_name}"

        pre_signed_post = s_3.generate_presigned_post(
            Bucket=bucket,
            Key=file_s3_path,
            Fields={"acl": "public-read", "Content-Type": content_type},
            Conditions=[
                {"acl": "public-read"},
                {"Content-Type": content_type}
            ],
            ExpiresIn=settings.S3_URL_LIFE
        )

        # Assign s3 path
        document.s3_path = f"s3://{bucket}/{file_s3_path}"
        document.save()

        return {
            'data': pre_signed_post,
            'document_id': document.id
        }


class DocumentSerializer(serializers.ModelSerializer):
    document_type = EnumField(DocumentType, ints_as_names=True)
    file_type = EnumField(FileType, ints_as_names=True)
    upload_status = EnumField(UploadStatus, ints_as_names=True)

    class Meta:
        model = Document
        exclude = ['shipment']
        read_only_fields = ('owner_id', 'shipment', 'document_type', 'file_type', 'size', 's3_path')

    class JSONAPIMeta:
        included_resources = ['shipment']


class DocumentUpdateSerializer(serializers.ModelSerializer):
    upload_status = EnumField(UploadStatus, ints_as_names=True)

    class Meta:
        model = Document
        fields = '__all__'
        read_only_fields = ('owner_id', 'shipment', 'document_type', 'file_type', 'size', 's3_path')


class DocumentRetrieveSerializer(serializers.ModelSerializer):
    document_type = EnumField(DocumentType, ints_as_names=True)
    file_type = EnumField(FileType, ints_as_names=True)
    upload_status = EnumField(UploadStatus, default=UploadStatus.COMPLETED, ints_as_names=True)
    url = serializers.ReadOnlyField(source='pre_signed_url')

    class Meta:
        model = Document
        exclude = ['s3_path', 'shipment']
        read_only_fields = ('owner_id', 'shipment', 'document_type', 'file_type', 'size', 'url')
