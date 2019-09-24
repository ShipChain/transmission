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

from django.conf import settings

from enumfields.drf import EnumSupportSerializerMixin
from rest_framework_json_api import serializers
from rest_framework import status
from shipchain_common.utils import UpperEnumField

from apps.utils import S3PreSignedMixin, UploadStatus
from .models import ShipmentImport, ProcessingStatus, FileType


class ShipmentImportSerializer(S3PreSignedMixin, EnumSupportSerializerMixin, serializers.ModelSerializer):
    file_type = UpperEnumField(FileType, lenient=True, read_only=True, ints_as_names=True)
    upload_status = UpperEnumField(UploadStatus, lenient=True, ints_as_names=True)
    processing_status = UpperEnumField(ProcessingStatus, lenient=True, ints_as_names=True)
    presigned_s3 = serializers.SerializerMethodField()
    _s3_bucket = settings.SHIPMENT_IMPORTS_BUCKET

    class Meta:
        model = ShipmentImport
        exclude = ('owner_id', 'masquerade_id', )
        read_only_fields = ('storage_credentials_id', 'shipper_wallet_id', 'carrier_wallet_id', )
        meta_fields = ('presigned_s3', )

    def get_presigned_s3(self, obj):
        if obj.upload_status != UploadStatus.COMPLETE:
            return super(ShipmentImportSerializer, self).get_presigned_s3(obj)
        return None


class ShipmentImportCreateSerializer(ShipmentImportSerializer):
    file_type = UpperEnumField(FileType, lenient=True, ints_as_names=True)
    upload_status = UpperEnumField(UploadStatus, lenient=True, ints_as_names=True, read_only=True)
    processing_status = UpperEnumField(ProcessingStatus, lenient=True, ints_as_names=True, read_only=True)

    class Meta:
        model = ShipmentImport
        if settings.PROFILES_ENABLED:
            exclude = ('owner_id', 'masquerade_id', )
        else:
            fields = '__all__'
        read_only_fields = ('upload_status', 'processing_status', )
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
