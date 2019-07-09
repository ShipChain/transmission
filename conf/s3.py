import boto3
from botocore.client import Config
from .base import ENVIRONMENT, BOTO3_SESSION


# s3 buckets names
S3_BUCKET = f"document-management-s3-{ENVIRONMENT.lower()}"
CSV_S3_BUCKET = f'document-management-s3-{ENVIRONMENT.lower()}-csv'

# s3 Pre-signed url life in seconds
S3_URL_LIFE = 1800
S3_MAX_BYTES = 12500000

# Supported Mime types
MIME_TYPE_MAP = {
    'pdf': 'application/pdf',
    'png': 'image/png',
    'jpg': 'image/jpeg',
    'jpeg': 'image/jpeg',
    'csv': 'text/csv',
    'xls': 'application/vnd.ms-excel',
    'xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
}

if ENVIRONMENT in ('PROD', 'DEMO', 'STAGE', 'DEV'):
    S3_CLIENT = BOTO3_SESSION.client('s3')
else:
    S3_CLIENT = boto3.client(
        's3',
        endpoint_url='http://minio:9000',
        config=Config(signature_version='s3v4'),
        region_name='us-east-1'
    )
