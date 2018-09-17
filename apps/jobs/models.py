import celery
from django.db import models
from django.conf import settings
from django.urls import reverse
# TODO: Should this be a Postgres field?
from django.contrib.postgres.fields import JSONField

from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType

from gm2m import GM2MField
from enumfields import Enum, EnumIntegerField

from apps.utils import random_id


class JobState(Enum):
    PENDING = 0
    RUNNING = 1
    FAILED = 2
    COMPLETE = 3


class AsyncJob(models.Model):
    id = models.CharField(primary_key=True, default=random_id, max_length=36)
    state = EnumIntegerField(JobState, default=JobState.PENDING)
    parameters = JSONField(blank=True, null=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)
    wallet_lock_token = models.CharField(blank=True, null=True, max_length=32)

    class Meta:
        ordering = ('created_at',)

    def get_callback_url(self):
        return settings.INTERNAL_URL + reverse('job-message', kwargs={'version': 'v1', 'pk': self.id})

    listeners = GM2MField('shipments.Shipment', through='JobListener')

    def fire(self, delay=None):
        # Use send_task to avoid cyclic import
        celery.current_app.send_task('apps.jobs.tasks.async_job_fire', (self.id,),
                                     countdown=delay * 60 if delay else None)

    @staticmethod
    def rpc_job_for_listener(rpc_method, rpc_parameters, signing_wallet_id, listener, delay=None):
        rpc_module = rpc_method.__module__
        rpc_class, rpc_method = rpc_method.__qualname__.rsplit('.')
        job = AsyncJob.objects.create(parameters={
            'rpc_class': f'{rpc_module}.{rpc_class}',
            'rpc_method': f'{rpc_method}',
            'rpc_parameters': rpc_parameters,
            'signing_wallet_id': signing_wallet_id,
        })
        job.joblistener_set.create(listener=listener)
        job.save()
        job.fire(delay)
        return job


class MessageType(Enum):
    ERROR = 0
    ETH_TRANSACTION = 1


class Message(models.Model):
    id = models.CharField(primary_key=True, default=random_id, max_length=36)

    async_job = models.ForeignKey(AsyncJob, on_delete=models.CASCADE)

    type = EnumIntegerField(MessageType)
    body = JSONField()
    created_at = models.DateTimeField(auto_now_add=True)


class JobListener(models.Model):
    async_job = models.ForeignKey(AsyncJob, on_delete=models.CASCADE)

    # Polymorphic listener
    listener_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    listener_id = models.CharField(max_length=36)
    listener = GenericForeignKey('listener_type', 'listener_id')
