import os

from celery.signals import setup_logging

from .custom_logging import LOGGING

CELERY_RESULT_BACKEND = os.environ.get('REDIS_URL', default='redis://:redis_pass@redis_db:6379/1')


@setup_logging.connect
def config_loggers(*args, **kwargs):
    # pylint-disable=import-outside-toplevel
    from logging.config import dictConfig
    dictConfig(LOGGING)
