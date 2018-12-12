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
    LOG.debug(f'Event post save with id {instance.id}.')

    # Update has been received, send signal to listener class
    if instance.eth_action:
        LOG.debug(f'Sending signals to all listeners for EthAction {instance.eth_action.transaction_hash}.')
        for listener in instance.eth_action.ethlistener_set.all():
            event_update.send(sender=listener.listener_type.model_class(),
                              event=instance, listener=listener.listener)

    if instance.event_name == 'Transfer':
        log_metric('transmission.info', tags={'method': 'event.transfer', 'module': __name__},
                   fields={'from_address': instance.return_values['from'],
                           'to_address': instance.return_values['to'],
                           'token_amount': float(instance.return_values['value'])/(10**18),
                           'count': 1})
