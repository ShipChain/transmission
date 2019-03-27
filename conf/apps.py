from .base import ENVIRONMENT

# The maximum length that Transmission will wait for a transaction to be confirmed before attempting to get a new nonce
WALLET_TIMEOUT = 900

# Celery retry intervals
CELERY_WALLET_RETRY = 30
CELERY_TXHASH_RETRY = 30

# Time in minutes to be used when rate limiting vault hash updates
TRACKING_VAULT_HASH_RATE_LIMIT = 120 if ENVIRONMENT == 'PROD' else 5
DATA_VAULT_HASH_RATE_LIMIT = 5

# Set default Shipment data version
SHIPMENT_SCHEMA_VERSION = "1.2.1"
