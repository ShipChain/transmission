import mimetypes
import boto3
from botocore.client import Config
from .base import ENVIRONMENT, BOTO3_SESSION


# s3 buckets names
DOCUMENT_MANAGEMENT_BUCKET = f"document-management-s3-{ENVIRONMENT.lower()}"
SHIPMENT_IMPORTS_BUCKET = f'shipment-imports-{ENVIRONMENT.lower()}'

# Mime types map
mimetypes.add_type('application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', '.xlsx')
MIME_TYPE_MAP = mimetypes.types_map

# s3 Pre-signed url life in seconds
S3_URL_LIFE = 1800
S3_MAX_BYTES = 12500000


if ENVIRONMENT in ('PROD', 'DEMO', 'STAGE', 'DEV'):
    S3_CLIENT = BOTO3_SESSION.client('s3',
                                     config=Config(s3={'use_accelerate_endpoint': True}))
else:
    S3_CLIENT = boto3.client(
        's3',
        endpoint_url='http://minio:9000',
        config=Config(signature_version='s3v4'),
        region_name='us-east-1'
    )
