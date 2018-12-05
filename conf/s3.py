import os
from .base import ENVIRONMENT

# s3 buckets names
S3_BUCKET = f"document-management-s3-{ENVIRONMENT.lower()}"

# s3 Pre-signed url life in seconds
S3_URL_LIFE = 1800

if ENVIRONMENT in ('PROD', 'DEMO', 'STAGE', 'DEV'):
    S3_ENDPOINT = 'https://s3.amazonaws.com'
else:
    AWS_ACCESS_KEY_ID = os.environ.get('AWS_SECRET_ACCESS_KEY', 'TEST-DEV-KEY')
    AWS_SECRET_ACCESS_KEY = os.environ.get('AWS_SECRET_ACCESS_KEY', 'NON-TRIVIAL-SECRETKEY')
    S3_ENDPOINT = 'http://minio:9000'
