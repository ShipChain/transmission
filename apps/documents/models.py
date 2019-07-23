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
from django.db import models
from enumfields import Enum
from enumfields import EnumIntegerField

from apps.shipments.models import Shipment
from apps.utils import UploadStatus, random_id


class DocumentType(Enum):
    BOL = 0
    IMAGE = 1
    OTHER = 2

    class Labels:
        BOL = 'BOL'
        IMAGE = 'IMAGE'
        OTHER = 'OTHER'


class FileType(Enum):
    """
    At the moment we do support just these three types
    """
    PDF = 0
    JPEG = 1
    PNG = 2

    class Labels:
        PDF = 'PDF'
        JPEG = 'JPEG'
        PNG = 'PNG'


class Document(models.Model):
    id = models.CharField(primary_key=True, default=random_id, max_length=36)
    name = models.CharField(max_length=36, null=False, blank=False)
    description = models.CharField(max_length=250, null=True, blank=True)
    owner_id = models.CharField(null=False, max_length=36)
    document_type = EnumIntegerField(enum=DocumentType, default=DocumentType.BOL)
    file_type = EnumIntegerField(enum=FileType, default=FileType.PDF)
    upload_status = EnumIntegerField(enum=UploadStatus, default=UploadStatus.PENDING)
    shipment = models.ForeignKey(Shipment, on_delete=models.CASCADE, null=False)
    updated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('updated_at',)

    @property
    def s3_key(self):
        return f"{self.storage_id}/{self.shipper_wallet_id}/{self.vault_id}/{self.filename}"

    @property
    def s3_path(self):
        return f"s3://{settings.DOCUMENT_MANAGEMENT_BUCKET}/{self.s3_key}"

    @property
    def filename(self):
        return f"{self.id}.{self.file_type.name.lower()}"

    @property
    def storage_id(self):
        return f"{self.shipment.storage_credentials_id}"

    @property
    def shipper_wallet_id(self):
        return f"{self.shipment.shipper_wallet_id}"

    @property
    def vault_id(self):
        return f"{self.shipment.vault_id}"
