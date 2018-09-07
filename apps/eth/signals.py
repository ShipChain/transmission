import logging

from django.db.models.signals import post_save
from django.dispatch import Signal, receiver
from influxdb_metrics.loader import log_metric

# pylint:disable=invalid-name
from apps.eth.models import Event

event_update = Signal(providing_args=["event", "listener"])
LOG = logging.getLogger('transmission')


@receiver(post_save, sender=Event, dispatch_uid='event_post_save')
def event_post_save(sender, instance, **kwargs):
    LOG.debug(f'Event post save with sender {sender}.')
    log_metric('transmission.info', tags={'method': 'event_post_save'})

    # Update has been received, send signal to listener class
    if instance.eth_action:
        LOG.debug(f'Update has been received, and signal sent to listener {listener}.')
        for listener in instance.eth_action.ethlistener_set.all():
            event_update.send(sender=listener.listener_type.model_class(),
                              event=instance, listener=listener.listener)
