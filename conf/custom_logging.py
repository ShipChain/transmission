import json

from .base import BOTO3_SESSION, ENVIRONMENT, LOG_LEVEL, PROFILES_ENABLED, SERVICE

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'celery-style': {
            'format': "[user:%(user_id)s Org:%(organization_id)s %(asctime)s: %(levelname)s/%(processName)s "
                      "%(filename)s:%(lineno)d] %(message)s",
        },
        'logstash-style': {
            '()': 'logstash_formatter.LogstashFormatter',
            'fmt': json.dumps({"extra": {"environment": ENVIRONMENT, "service": SERVICE}}),
        }
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'celery-style',
            'filters': []
        },
        'organization_id': {
            'class': 'logging.StreamHandler',
            'level': LOG_LEVEL,
        },
        'user_id': {
            'class': 'logging.StreamHandler',
            'level': LOG_LEVEL,
        },
    },
    'filters': {
        'organization_id': {
            '()': 'custom_logging.filter.OrganizationIdFilter',
        },
        'user_id': {
            '()': 'custom_logging.filter.UserIdFilter',
        },
    },

    'loggers': {
        'django.template': {
            # Get rid of noisy debug messages
            'handlers': ['console'],
            'level': 'INFO' if LOG_LEVEL == 'DEBUG' else LOG_LEVEL,
            'propagate': False,
        },
        'django.utils.autoreload': {
            'handlers': ['console'],
            'level': 'INFO' if LOG_LEVEL == 'DEBUG' else LOG_LEVEL,
            'propagate': False,
        },
        'django': {
            'handlers': ['console'],
            'level': LOG_LEVEL,
        },
        'transmission': {
            'handlers': ['console'],
            'level': LOG_LEVEL,
            'filters': []
        },
    }
}


if PROFILES_ENABLED:
    # Handlers config
    LOGGING['handlers']['console']['filters'].extend(['organization_id', 'user_id'])

    # Loggers config
    LOGGING['loggers']['transmission']['filters'].extend(['user_id', 'organization_id'])


if BOTO3_SESSION:
    LOGGING['handlers']['cloudwatch'] = {
        'class': 'watchtower.CloudWatchLogHandler',
        'boto3_session': BOTO3_SESSION,
        'log_group': f'transmission-django-{ENVIRONMENT}',
        'create_log_group': True,
        'stream_name': 'logs-' + SERVICE + '-{strftime:%Y-%m-%d}',
        'formatter': 'logstash-style',
        'use_queues': False,
    }
    LOGGING['loggers']['django']['handlers'].append('cloudwatch')
    LOGGING['loggers']['transmission']['handlers'].append('cloudwatch')
