import logging

from apps.eth.models import Event
from apps.rpc_client import RPCClient, RPCError
from influxdb_metrics.loader import log_metric


LOG = logging.getLogger('transmission')


class EventRPCClient(RPCClient):

    def subscribe(self, url=Event.get_event_subscription_url(), project="LOAD", interval=5000, events=None):
        LOG.debug(f'Event subscription with url {url}.')
        log_metric('transmission.info', tags={'method': 'event.subscribe'})

        result = self.call('event.subscribe', {
            "url": url,
            "project": project,
            "interval": interval,
            "eventNames": events or ["allEvents"],
        })

        if 'success' in result and result['success']:
            if 'subscription' in result:
                return

        raise RPCError("Invalid response from Engine")
