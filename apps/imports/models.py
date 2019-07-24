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

from enumfields import Enum
from enumfields import EnumIntegerField

from django.contrib.postgres.fields import JSONField
from django.db import models

from apps.utils import UploadStatus, random_id


class FileType(Enum):
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
    owner_id = models.CharField(null=False, max_length=36)
    masquerade_id = models.CharField(null=False, max_length=36)
    description = models.CharField(max_length=250, null=True, blank=True)
    file_type = EnumIntegerField(enum=FileType, default=FileType.CSV)
    upload_status = EnumIntegerField(enum=UploadStatus, default=UploadStatus.PENDING)
    processing_status = EnumIntegerField(enum=ProcessingStatus, default=ProcessingStatus.PENDING)
    report = JSONField(blank=True, null=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('updated_at',)

    @property
    def s3_key(self):
        return f"{self.masquerade_id}/{self.filename}"

    @property
    def filename(self):
        return f"{self.id}.{self.file_type.name.lower()}"
