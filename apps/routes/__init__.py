from django.apps import AppConfig


class RoutesConfig(AppConfig):
    name = 'apps.routes'
    label = 'routes'
    verbose_name = 'routes'

    def ready(self):
        # pylint:disable=unused-import
        import apps.routes.signals


# pylint:disable=invalid-name
default_app_config = 'apps.routes.RoutesConfig'
