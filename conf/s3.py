import boto3
from botocore.client import Config
from .base import ENVIRONMENT


# s3 buckets names
S3_BUCKET = f"document-management-s3-{ENVIRONMENT.lower()}"

# s3 Pre-signed url life in seconds
S3_URL_LIFE = 1800
S3_MAX_BYTES = 12500000

if ENVIRONMENT in ('PROD', 'DEMO', 'STAGE', 'DEV'):
    S3_CLIENT = boto3.client('s3', region_name='us-east-1')
else:
    S3_CLIENT = boto3.client(
        's3',
        endpoint_url='http://minio:9000',
        config=Config(signature_version='s3v4'),
        region_name='us-east-1'
    )
