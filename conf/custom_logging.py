from .base import LOGGING, LOG_LEVEL, PROFILES_ENABLED

if PROFILES_ENABLED:
    # Filters config
    LOGGING['filters'] = {
        'organization_id': {
            '()': 'custom_logging.filter.OrganizationIdFilter',
        },
        'user_id': {
            '()': 'custom_logging.filter.UserIdFilter',
        },
    }

    # Handlers config
    LOGGING['handlers']['console']['filters'] = ['organization_id', 'user_id']
    LOGGING['handlers']['organization_id'] = {
        'class': 'logging.StreamHandler',
        'level': LOG_LEVEL,
    }
    LOGGING['handlers']['user_id'] = {
        'class': 'logging.StreamHandler',
        'level': LOG_LEVEL,
    }

    # Loggers config
    LOGGING['loggers']['transmission']['filters'] = ['user_id', 'organization_id']


