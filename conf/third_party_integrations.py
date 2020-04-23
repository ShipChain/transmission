import os
from .base import BOTO3_SESSION, ENVIRONMENT

AFTERSHIP_URL = 'https://api.aftership.com/v4/'
AFTERSHIP_API_KEY = os.environ.get('AFTERSHIP_API_KEY', None)

SNS_ARN = os.environ.get('SNS_ARN', None)
SNS_CLIENT = BOTO3_SESSION.client('sns') if ENVIRONMENT in ('PROD', 'DEMO', 'STAGE', 'DEV') else None
