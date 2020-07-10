from django.apps import AppConfig
from django.conf import settings


class EthConfig(AppConfig):
    name = 'apps.eth'
    label = 'eth'
    verbose_name = 'Eth'

    def ready(self):
        # pylint:disable=unused-import,import-outside-toplevel
        import apps.eth.signals

        if settings.SUBSCRIBE_EVENTS:
            # We move this import here to avoid triggering AppRegistryNotReady exception
            from .tasks import engine_subscribe_load, engine_subscribe_token

            engine_subscribe_load.delay()  # Handle subscription via Celery task
            engine_subscribe_token.delay()  # Handle subscription via Celery task


# pylint:disable=invalid-name
default_app_config = 'apps.eth.EthConfig'
