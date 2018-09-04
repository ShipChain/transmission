from django.apps import AppConfig


class ShipmentsConfig(AppConfig):
    name = 'apps.shipments'
    label = 'shipments'
    verbose_name = 'shipments'

    def ready(self):
        # pylint:disable=unused-variable
        import apps.shipments.signals


# pylint:disable=invalid-name
default_app_config = 'apps.shipments.ShipmentsConfig'
