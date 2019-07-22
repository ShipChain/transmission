from enumfields import Enum
from enumfields import EnumIntegerField

from django.contrib.postgres.fields import JSONField
from django.db import models

from apps.utils import UploadStatus, random_id


class ShipmentUploadFileType(Enum):
    CSV = 0
    XLS = 1
    XLSX = 2

    class Labels:
        CSV = 'CSV'
        XLS = 'XLS'
        XLSX = 'XLSX'


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


class ShipmentImport(models.Model):
    id = models.CharField(primary_key=True, default=random_id, max_length=36)
    name = models.CharField(max_length=36, null=False, blank=False)
    storage_credentials_id = models.CharField(null=False, max_length=36)
    shipper_wallet_id = models.CharField(null=False, max_length=36)
    carrier_wallet_id = models.CharField(null=False, max_length=36)
    user_id = models.CharField(null=False, max_length=36)
    description = models.CharField(max_length=250, null=True, blank=True)
    file_type = EnumIntegerField(enum=ShipmentUploadFileType, default=ShipmentUploadFileType.CSV)
    upload_status = EnumIntegerField(enum=UploadStatus, default=UploadStatus.PENDING)
    processing_status = EnumIntegerField(enum=ProcessingStatus, default=ProcessingStatus.PENDING)
    report = JSONField(blank=True, null=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('updated_at',)

    @property
    def s3_key(self):
        return f"{self.user_id}/{self.filename}"

    @property
    def filename(self):
        return f"{self.id}.{self.file_type.name.lower()}"
