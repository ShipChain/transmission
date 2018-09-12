import logging
from redis.lock import LockError

from django.core.cache import cache
from django.db.models.signals import post_save
from django.dispatch import Signal, receiver
from influxdb_metrics.loader import log_metric

from .models import Message, MessageType, JobState

# pylint:disable=invalid-name
job_update = Signal(providing_args=["message", "listener"])

LOG = logging.getLogger('transmission')


@receiver(post_save, sender=Message, dispatch_uid='message_post_save')
def message_post_save(sender, instance, **kwargs):
    LOG.debug(f'Message post save with message {instance.id}.')
    log_metric('transmission.info', tags={'method': 'jobs.message_post_save'})
    try:
        wallet_lock = cache.lock(instance.async_job.parameters['signing_wallet_id'])
        wallet_lock.local.token = instance.async_job.wallet_lock_token
        wallet_lock.release()
    except LockError:
        LOG.warning(f'Wallet {instance.async_job.parameters["signing_wallet_id"]} was not locked when '
                    f'job {instance.async_job.id} received message {instance.id}')
    if instance.type == MessageType.ERROR:
        # Generic error handling
        logging.error(f"Transaction failure for AsyncJob {instance.async_job.id}: {instance.body}")
        instance.async_job.state = JobState.FAILED
        instance.async_job.save()

    # Update has been received, send signal to listener class
    for listener in instance.async_job.joblistener_set.all():
        LOG.debug(f'Update has been received, and signal sent to listener {listener}.')
        job_update.send(sender=listener.listener_type.model_class(),
                        message=instance, listener=listener.listener)
