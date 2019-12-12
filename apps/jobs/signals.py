import logging

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.core.cache import cache
from django.db.models.signals import post_save
from django.dispatch import Signal, receiver
from redis.lock import LockError
from influxdb_metrics.loader import log_metric

from apps.shipments.models import Shipment
from .models import AsyncJob, Message, MessageType, JobState

# pylint:disable=invalid-name
job_update = Signal(providing_args=["message", "shipment"])
channel_layer = get_channel_layer()
LOG = logging.getLogger('transmission')


@receiver(post_save, sender=AsyncJob, dispatch_uid='asyncjob_post_save')
def asyncjob_post_save(sender, instance, **kwargs):
    # Notify websockets of any AsyncJob create/updates
    async_to_sync(channel_layer.group_send)(instance.shipment.owner_id,
                                            {"type": "jobs.update", "async_job_id": instance.id})


@receiver(post_save, sender=Message, dispatch_uid='message_post_save')
def message_post_save(sender, instance, **kwargs):
    LOG.debug(f'Message post save with message {instance.id}.')
    log_metric('transmission.info', tags={'method': 'jobs.message_post_save', 'module': __name__})
    try:
        wallet_lock = cache.lock(instance.async_job.parameters['signing_wallet_id'])
        wallet_lock.local.token = instance.async_job.wallet_lock_token
        wallet_lock.release()
    except LockError:
        LOG.warning(f'Wallet {instance.async_job.parameters["signing_wallet_id"]} was not locked when '
                    f'job {instance.async_job.id} received message {instance.id}')
    if instance.type == MessageType.ERROR:
        # Generic error handling
        LOG.error(f"Transaction failure for AsyncJob {instance.async_job.id}: {instance.body}")
        instance.async_job.state = JobState.FAILED
        instance.async_job.save()

    # Update has been received, send signal to listener
    LOG.debug(f'Update has been received, and signal sent to listener {instance.id}.')
    job_update.send(sender=Shipment, message=instance, shipment=instance.async_job.shipment)
