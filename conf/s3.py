import os
import boto3
from botocore.client import Config
from .base import ENVIRONMENT


# s3 buckets names
S3_BUCKET = f"document-management-s3-{ENVIRONMENT.lower()}"

# s3 Pre-signed url life in seconds
S3_URL_LIFE = 1800

if ENVIRONMENT in ('PROD', 'DEMO', 'STAGE', 'DEV'):
    S3_ENDPOINT = 'https://s3.amazonaws.com'
    S3_CLIENT = boto3.client('s3', region_name='us-east-1')
else:
    AWS_ACCESS_KEY_ID = os.environ.get('AWS_ACCESS_KEY_ID', 'TEST-DEV-KEY')
    AWS_SECRET_ACCESS_KEY = os.environ.get('AWS_SECRET_ACCESS_KEY', 'NON-TRIVIAL-SECRETKEY')
    S3_ENDPOINT = 'http://minio:9000'
    S3_CLIENT = boto3.client(
        's3',
        endpoint_url=S3_ENDPOINT,
        aws_access_key_id=AWS_ACCESS_KEY_ID,
        aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
        config=Config(signature_version='s3v4'),
        region_name='us-east-1'
    )
