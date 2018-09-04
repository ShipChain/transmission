import logging

from django.db.models.signals import post_save
from django.dispatch import Signal, receiver

from .models import Message, MessageType, JobState

# pylint:disable=invalid-name
job_update = Signal(providing_args=["message", "listener"])

LOG = logging.getLogger('transmission')


@receiver(post_save, sender=Message, dispatch_uid='message_post_save')
def message_post_save(sender, instance, **kwargs):
    if instance.type == MessageType.ERROR:
        # Generic error handling
        logging.error(f"Transaction failure for AsyncJob {instance.async_job.id}: {instance.body}")
        instance.async_job.state = JobState.FAILED
        instance.async_job.save()

    # Update has been received, send signal to listener class
    for listener in instance.async_job.joblistener_set.all():
        job_update.send(sender=listener.listener_type.model_class(),
                        message=instance, listener=listener.listener)
