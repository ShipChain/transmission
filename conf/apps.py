from .base import ENVIRONMENT

# The maximum length that Transmission will wait for a transaction to be confirmed before attempting to get a new nonce
WALLET_TIMEOUT = 900

# The maximum timeout that Transmission will 'lock' a vault_id, preventing concurrent vault writes
VAULT_TIMEOUT = 120

# Celery retry intervals
CELERY_WALLET_RETRY = 30
CELERY_TXHASH_RETRY = 30

# Time in minutes to be used when rate limiting vault hash updates
DEFAULT_BACKGROUND_DATA_HASH_INTERVAL = 120 if ENVIRONMENT == 'PROD' else 5
DEFAULT_MANUAL_UPDATE_HASH_INTERVAL = 5

# Set default Shipment data version
SHIPMENT_SCHEMA_VERSION = "1.2.3"
