from django.apps import AppConfig


class JobsConfig(AppConfig):
    name = 'apps.jobs'
    label = 'jobs'
    verbose_name = 'Jobs'

    def ready(self):
        # pylint:disable=unused-import,import-outside-toplevel
        import apps.jobs.signals


# pylint:disable=invalid-name
default_app_config = 'apps.jobs.JobsConfig'
