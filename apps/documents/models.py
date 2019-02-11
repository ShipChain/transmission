import logging

from django.conf import settings
from django.db import models
from enumfields import Enum
from enumfields import EnumIntegerField

from apps.shipments.models import Shipment
from apps.utils import random_id

LOG = logging.getLogger('transmission')


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


IMAGE_TYPES = (FileType.JPEG.name.lower(), FileType.PNG.name.lower())


class UploadStatus(Enum):
    PENDING = 0
    COMPLETE = 1
    FAILED = 2

    class Labels:
        PENDING = 'PENDING'
        COMPLETE = 'COMPLETE'
        FAILED = 'FAILED'


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
    accessed_from_vault_at = models.DateField(null=True, blank=True)

    @property
    def s3_key(self):
        return f"{self.shipment.storage_credentials_id}/{self.shipment.shipper_wallet_id}" \
            f"/{self.shipment.vault_id}/{self.id}.{self.file_type.name.lower()}"

    @property
    def s3_path(self):
        return f"s3://{settings.S3_BUCKET}/{self.s3_key}"
