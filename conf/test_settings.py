from cryptography.hazmat.primitives.asymmetric import rsa


from conf import *

ENVIRONMENT = 'TEST'
INFLUXDB_DISABLED = True

# Disable auth for unit tests
REST_FRAMEWORK['DEFAULT_AUTHENTICATION_CLASSES'] = []
REST_FRAMEWORK['DEFAULT_PERMISSION_CLASSES'] = []

ENGINE_RPC_URL = "http://INTENTIONALLY_DISCONNECTED:9999"
INTERNAL_URL = "http://INTENTIONALLY_DISCONNECTED:9999"
PROFILES_URL = "http://INTENTIONALLY_DISCONNECTED:9999"

IOT_THING_INTEGRATION = True
IOT_AWS_HOST = 'not-really-aws.com'
IOT_GATEWAY_STAGE = 'test'

SUBSCRIBE_EVENTS = False

for name, logger in LOGGING['loggers'].items():
    logger['handlers'] = [h for h in logger.get('handlers', []) if h != 'elasticsearch']
    if logger.get('level') == 'DEBUG':
        logger['level'] = 'INFO'

SIMPLE_JWT['PRIVATE_KEY'] = rsa.generate_private_key(public_exponent=65537, key_size=2048, backend=default_backend())
SIMPLE_JWT['VERIFYING_KEY'] = SIMPLE_JWT['PRIVATE_KEY'].public_key()

S3_RESOURCE = boto3.resource(
    's3',
    endpoint_url='http://minio:9000',
    config=Config(signature_version='s3v4'),
    region_name='us-east-1'
)

CACHES['page'] = {'BACKEND': 'django.core.cache.backends.dummy.DummyCache'}
