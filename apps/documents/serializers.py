from collections import OrderedDict

import json
import boto3
from botocore.client import Config
from botocore.exceptions import ClientError
from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from django.conf import settings
from django.db import transaction
from enumfields.drf import EnumField
from enumfields.drf.serializers import EnumSupportSerializerMixin
from jose import jws, JWSError
from rest_framework import exceptions
from rest_framework import status
from rest_framework.utils import model_meta
from rest_framework.fields import SkipField
from rest_framework_json_api import serializers
from rest_framework.utils.serializer_helpers import ReturnList

from .models import Document, DocumentType, FileType, UploadStatus
from apps.utils import get_s3_client
from apps.shipments.serializers import ShipmentSerializer
from apps.shipments.models import Shipment


class DocumentCreateSerializer(serializers.ModelSerializer):
    """
    Model serializer for pdf documents validation for s3 signing
    """
    document_type = EnumField(DocumentType, ints_as_names=True)
    file_type = EnumField(FileType, ints_as_names=True)
    upload_status = EnumField(UploadStatus, ints_as_names=True)
    shipment_id = serializers.CharField(max_length=36)

    class Meta:
        model = Document
        fields = ['document_type', 'file_type', 'size', 'upload_status', 'shipment_id']

    def s3_sign(self, document=None):
        data = self.validated_data
        s3, _ = get_s3_client()
        bucket = settings.S3_BUCKET
        file_type = data['file_type']
        file_s3_path = f"{document.shipment.id}/{document.id}.pdf"

        pre_signed_post = s3.generate_presigned_post(
            Bucket=bucket,
            Key=file_s3_path,
            Fields={"acl": "public-read", "Content-Type": f'application/{file_type.name.lower()}'},
            Conditions=[
                {"acl": "public-read"},
                {"Content-Type": f'application/{file_type.name.lower()}'}
            ],
            ExpiresIn=1800
        )

        return {
            'data': pre_signed_post,
            'path': f"{bucket}/{file_s3_path}"
        }


class DocumentSerializer(serializers.ModelSerializer):
    document_type = EnumField(DocumentType, ints_as_names=True)
    file_type = EnumField(FileType, ints_as_names=True)
    upload_status = EnumField(UploadStatus, ints_as_names=True)

    class Meta:
        model = Document
        # fields = '__all__'
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


class DocumentListSerializer(serializers.ListSerializer):
    """
    This custom class allows us to add to the returned documents the one time s3 generated url
    """
    @property
    def data(self):
        # pass
        data = super(DocumentListSerializer, self).data
        super(DocumentListSerializer, self).data

        for d in data:
            # We clean the list of documents form the one not uploaded to s3
            if d['upload_status'] != 'completed':
                data.pop(data.index(d))
            else:
                doc = Document.objects.get(id=d['id'])
                d.update({'s3_url': doc.generate_presigned_url})

        return ReturnList(data, serializer=self)


class DocumentRetrieveSerializer(serializers.ModelSerializer):
    document_type = EnumField(DocumentType, ints_as_names=True)
    file_type = EnumField(FileType, ints_as_names=True)
    upload_status = EnumField(UploadStatus, default=UploadStatus.COMPLETED, ints_as_names=True)

    class Meta:
        model = Document
        exclude = ['s3_path', 'shipment']
        read_only_fields = ('owner_id', 'shipment', 'document_type', 'file_type', 'size')

    @classmethod
    def many_init(cls, *args, **kwargs):
        kwargs['child'] = cls()
        return DocumentListSerializer(*args, **kwargs)

    def validate_upload_status(self):
        instance = self.instance
        if instance.upload_status != UploadStatus.COMPLETED:
            raise serializers.ValidationError('This document does not exist!')
        return True

    @property
    def data(self):
        """
        We override the returned data to include the one time s3 generated url
        """
        if not hasattr(self, '_data'):
            if self.instance is not None and not getattr(self, '_errors', None):
                self._data = self.to_representation(self.instance)
            elif hasattr(self, '_validated_data') and not getattr(self, '_errors', None):
                self._data = self.to_representation(self.validated_data)
            else:
                self._data = self.get_initial()

        self._data.update({'s3_url': self.instance.generate_presigned_url})

        super(DocumentRetrieveSerializer, self).data

        return self._data
# class DocumentCreateSerializer(DocumentSerializer):
#
#     def __init__(self, *args, **kwargs):
#         try:
#             # print(kwargs)
#             shipment_id = kwargs['data'].get('shipment_id', None)
#             kwargs['data']['shipment'] = Shipment.objects.get(pk=shipment_id)
#         except Shipment.DoesNotExist:
#             raise exceptions.NotFound(f'Shipment: {shipment_id}')
#         except Shipment.MultipleObjectsReturned:
#             raise exceptions.APIException(f'Multiple values returned for:{shipment_id}')
#         # kwargs.pop('shipment_id')
#         super().__init__(self, *args, **kwargs)

    # def validate(self, data):
    #     print(data)
    #     super().validate(self, data)

    # def create(self, validated_data):
    #     return Document.objects.create(** validated_data)