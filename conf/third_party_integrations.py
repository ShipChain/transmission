import os

AFTERSHIP_URL = 'https://api.aftership.com/v4/'
AFTERSHIP_API_KEY = os.environ.get('AFTERSHIP_API_KEY', None)


SNS_ARN = os.environ.get('SNS_ARN', None)
