from django.db import migrations


def migrate_asyncjobs(apps, schema_editor):
    AsyncJob = apps.get_model('jobs', 'AsyncJob')
    pending_jobs = AsyncJob.objects.filter(state__lt=3, parameters__rpc_method='create_shipment_transaction')
    for job in pending_jobs:
        params = job.parameters['rpc_parameters']
        if len(params) == 4:
            job.parameters['rpc_parameters'] = params[:2]
            job.save()


class Migration(migrations.Migration):
    dependencies = [
        ('jobs', '0001_squashed_091919'),
    ]

    operations = [
        migrations.RunPython(migrate_asyncjobs, reverse_code=migrations.RunPython.noop),
    ]