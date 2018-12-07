import logging

from django.conf import settings
from django.db import models
from enumfields import Enum
from enumfields import EnumIntegerField
from influxdb_metrics.loader import log_metric

from apps.shipments.models import Shipment
from apps.utils import random_id

LOG = logging.getLogger('transmission')


class DocumentType(Enum):
    BOL = 0
    IMAGE = 1
    OTHER = 2


class FileType(Enum):
    """
    At the moment we do support just these three types
    """
    PDF = 0
    JPEG = 1
    PNG = 2


IMAGE_TYPES = (FileType.JPEG, FileType.PNG)


class UploadStatus(Enum):
    PENDING = 0
    COMPLETED = 1
    FAILED = 2


class Document(models.Model):
    id = models.CharField(primary_key=True, default=random_id, max_length=36)
    name = models.CharField(max_length=36, null=False, blank=False)
    description = models.CharField(max_length=250, null=True, blank=True)
    owner_id = models.CharField(null=False, max_length=36)
    document_type = EnumIntegerField(enum=DocumentType, default=DocumentType.BOL)
    file_type = EnumIntegerField(enum=FileType, default=FileType.PDF)
    upload_status = EnumIntegerField(enum=UploadStatus, default=UploadStatus.PENDING)
    s3_path = models.CharField(max_length=252, blank=False, null=False)
    shipment = models.ForeignKey(Shipment, on_delete=models.CASCADE, null=False)
    updated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def pre_signed_url(self):
        s3_client = settings.S3_CLIENT

        url = s3_client.generate_presigned_url(
            'get_object',
            Params={
                'Bucket': f"{settings.S3_BUCKET}",
                'Key': '/'.join(self.s3_path.split('/')[3:])
            },
            ExpiresIn=settings.S3_URL_LIFE
        )

        if self.upload_status != UploadStatus.COMPLETED:
            return None

        LOG.debug(f'Generated one time s3 url for: {self.id}')
        log_metric('transmission.info', tags={'method': 'documents.generate_presigned_url', 'module': __name__})

        return url
