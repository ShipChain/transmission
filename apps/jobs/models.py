import celery
from django.db import models, transaction
from django.conf import settings
from django.urls import reverse
# TODO: Should this be a Postgres field?
from django.contrib.postgres.fields import JSONField
from enumfields import Enum, EnumIntegerField
from shipchain_common.utils import random_id

from apps.eth.fields import HashField


class JobState(Enum):
    PENDING = 0
    RUNNING = 1
    FAILED = 2
    COMPLETE = 3

    class Labels:
        PENDING = 'PENDING'
        RUNNING = 'RUNNING'
        FAILED = 'FAILED'
        COMPLETE = 'COMPLETE'


class AsyncJob(models.Model):
    id = models.CharField(primary_key=True, default=random_id, max_length=36)
    state = EnumIntegerField(JobState, default=JobState.PENDING)
    parameters = JSONField(blank=True, null=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)
    wallet_lock_token = models.CharField(blank=True, null=True, max_length=32)

    last_try = models.DateTimeField(null=True)
    delay = models.IntegerField(default=0)

    class Meta:
        ordering = ('created_at',)

    def get_callback_url(self):
        return settings.INTERNAL_URL + reverse('job-message', kwargs={'version': 'v1', 'pk': self.id})

    shipment = models.ForeignKey('shipments.Shipment', on_delete=models.CASCADE)

    def fire(self, delay=None):
        # Use send_task to avoid cyclic import
        celery.current_app.send_task('apps.jobs.tasks.async_job_fire', task_id=self.id,
                                     countdown=delay * 60 if delay else None)

    def get_task(self):
        return celery.current_app.AsyncResult(self.id)

    @staticmethod
    def rpc_job_for_listener(rpc_method, rpc_parameters, signing_wallet_id, shipment, delay=0):
        rpc_module = rpc_method.__module__
        rpc_class, rpc_method = rpc_method.__qualname__.rsplit('.')[-2:]
        with transaction.atomic():
            job = AsyncJob.objects.create(parameters={
                'rpc_class': f'{rpc_module}.{rpc_class}',
                'rpc_method': f'{rpc_method}',
                'rpc_parameters': rpc_parameters,
                'signing_wallet_id': signing_wallet_id,
            }, shipment=shipment, delay=delay)
            transaction.on_commit(lambda: job.fire(delay))
        return job


class AsyncActionType(Enum):
    UNKNOWN = 0
    TRACKING = 1
    SHIPMENT = 2
    DOCUMENT = 3
    TELEMETRY = 4

    class Labels:
        UNKNOWN = 'Unknown'
        TRACKING = 'Tracking Data'
        SHIPMENT = 'Shipment Update'
        DOCUMENT = 'Document Upload'
        TELEMETRY = 'Telemetry Data'


class AsyncAction(models.Model):
    id = models.CharField(primary_key=True, default=random_id, max_length=36)
    async_job = models.ForeignKey(AsyncJob, on_delete=models.CASCADE, related_name='actions')
    user_id = models.CharField(blank=True, null=True, max_length=36)
    action_type = EnumIntegerField(AsyncActionType, default=AsyncActionType.UNKNOWN)
    vault_hash = HashField(blank=True)

    updated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('created_at',)


class MessageType(Enum):
    ERROR = 0
    ETH_TRANSACTION = 1

    class Labels:
        ERROR = 'ERROR'
        ETH_TRANSACTION = 'ETH_TRANSACTION'


class Message(models.Model):
    id = models.CharField(primary_key=True, default=random_id, max_length=36)

    async_job = models.ForeignKey(AsyncJob, on_delete=models.CASCADE)

    type = EnumIntegerField(MessageType)
    body = JSONField()
    created_at = models.DateTimeField(auto_now_add=True)
