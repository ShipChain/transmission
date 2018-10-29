from conf import *

ENVIRONMENT = 'TEST'
INFLUXDB_DISABLED = True

# Disable auth for unit tests
REST_FRAMEWORK['DEFAULT_AUTHENTICATION_CLASSES'] = []
REST_FRAMEWORK['DEFAULT_PERMISSION_CLASSES'] = []

ENGINE_RPC_URL = "http://INTENTIONALLY_DISCONNECTED:9999"
INTERNAL_URL = "http://INTENTIONALLY_DISCONNECTED:9999"
PROFILES_URL = "http://INTENTIONALLY_DISCONNECTED:9999"

SUBSCRIBE_EVENTS = False

for name, logger in LOGGING['loggers'].items():
    logger['handlers'] = [h for h in logger.get('handlers', []) if h != 'elasticsearch']
    if logger.get('level') == 'DEBUG':
        logger['level'] = 'INFO'
