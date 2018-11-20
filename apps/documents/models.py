import logging
from datetime import datetime, timedelta
import pytz

import boto3

from django.conf import settings
from django.contrib.postgres.fields import JSONField
from django.core.validators import RegexValidator, MinValueValidator, MaxValueValidator
from django.db import models
from enumfields import Enum
from enumfields import EnumField

from apps.shipments.models import Shipment
from apps.utils import random_id, get_s3_client

LOG = logging.getLogger('transmission')


class DocumentType(Enum):
    BOL = 0
    OTHER = 1


class FileType(Enum):
    """
    At the moment we do support just pdf documents type
    """
    PDF = 0
    # OTHER = 1


class UploadStatus(Enum):
    PENDING = 0
    COMPLETED = 1
    FAILED = 2


class Document(models.Model):
    id = models.CharField(primary_key=True, default=random_id, max_length=36)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    owner_id = models.CharField(null=False, max_length=36)
    document_type = EnumField(enum=DocumentType, default=DocumentType.BOL)
    file_type = EnumField(enum=FileType, default=FileType.PDF)
    upload_status = EnumField(enum=UploadStatus, default=UploadStatus.PENDING)
    size = models.IntegerField(validators=[MinValueValidator(1), MaxValueValidator(1250000)])
    s3_path = models.CharField(max_length=144, blank=True, null=True)
    shipment = models.ForeignKey(Shipment, on_delete=models.CASCADE, null=False)

    def assign_s3_path(self, path=None):
        self.s3_path = path
        self.save()

    @property
    def generate_presigned_url(self):
        s3, _ = get_s3_client()
        key = '/'.join(self.s3_path.split('/')[1:])
        url = s3.generate_presigned_url('get_object', Params={
                'Bucket': f"{settings.S3_BUCKET}",
                'Key': key
            }, ExpiresIn=settings.S3_URL_LIFE
        )

        return url
