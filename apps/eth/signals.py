import logging

from django.db.models.signals import post_save
from django.dispatch import Signal, receiver

# pylint:disable=invalid-name
from apps.eth.models import Event
from apps.shipments.models import Shipment


event_update = Signal(providing_args=["event", "shipment"])
LOG = logging.getLogger('transmission')


@receiver(post_save, sender=Event, dispatch_uid='event_post_save')
def event_post_save(sender, instance, **kwargs):
    LOG.debug(f'Event post save with id {instance.id}.')

    # Update has been received, send signal to listener class
    if instance.eth_action:
        LOG.debug(f'Sending signals to Shipment for EthAction {instance.eth_action.transaction_hash}.')
        event_update.send(sender=Shipment, event=instance, shipment=instance.eth_action.shipment)
