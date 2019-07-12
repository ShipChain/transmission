import logging

from django.conf import settings
from django.contrib.postgres.fields import JSONField
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


class CsvFileType(Enum):
    CSV = 0
    XLS = 1
    XLSX = 2

    class Labels:
        CSV = 'CSV'
        XLS = 'XLS'
        XLSX = 'XLSX'


class UploadStatus(Enum):
    PENDING = 0
    COMPLETE = 1
    FAILED = 2

    class Labels:
        PENDING = 'PENDING'
        COMPLETE = 'COMPLETE'
        FAILED = 'FAILED'


class ProcessingStatus(Enum):
    PENDING = 0
    RUNNING = 1
    COMPLETE = 2
    FAILED = 3

    class Labels:
        PENDING = 'PENDING'
        RUNNING = 'RUNNING'
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

    class Meta:
        ordering = ('updated_at',)

    @property
    def s3_key(self):
        return f"{self.storage_id}/{self.shipper_wallet_id}/{self.vault_id}/{self.filename}"

    @property
    def s3_path(self):
        return f"s3://{settings.S3_BUCKET}/{self.s3_key}"

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


class CsvDocument(models.Model):
    id = models.CharField(primary_key=True, default=random_id, max_length=36)
    name = models.CharField(max_length=36, null=False, blank=False)
    storage_credentials_id = models.CharField(null=False, max_length=36)
    shipper_wallet_id = models.CharField(null=False, max_length=36)
    carrier_wallet_id = models.CharField(null=False, max_length=36)
    owner_id = models.CharField(null=False, max_length=36)
    updated_by = models.CharField(null=False, max_length=36)
    description = models.CharField(max_length=250, null=True, blank=True)
    csv_file_type = EnumIntegerField(enum=CsvFileType, default=CsvFileType.CSV)
    upload_status = EnumIntegerField(enum=UploadStatus, default=UploadStatus.PENDING)
    processing_status = EnumIntegerField(enum=ProcessingStatus, default=ProcessingStatus.PENDING)
    report = JSONField(blank=True, null=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('updated_at',)

    @property
    def s3_key(self):
        return f"{self.storage_credentials_id}/{self.shipper_wallet_id}/{self.carrier_wallet_id}/" \
            f"{self.updated_by}/{self.filename}"

    @property
    def filename(self):
        return f"{self.id}.{self.csv_file_type.name.lower()}"
