import logging

from influxdb_metrics.loader import log_metric

from apps.eth.models import Event
from apps.rpc_client import RPCClient, RPCError

LOG = logging.getLogger('transmission')


class EventRPCClient(RPCClient):

    def subscribe(self, project, version, url=Event.get_event_subscription_url(), interval=5000,
                  events=None):
        LOG.debug(f'Event subscription with url {url}.')
        log_metric('transmission.info', tags={'method': 'event_rpcclient.subscribe',
                                              'module': __name__})

        result = self.call('event.subscribe', {
            "url": url,
            "project": project,
            "interval": interval,
            "eventNames": events or ["allEvents"],
            "version": version
        })

        if 'success' in result and result['success']:
            if 'subscription' in result:
                return

        log_metric('transmission.error', tags={'method': 'event_rpcclient.subscribe', 'code': 'RPCError',
                                               'module': __name__})
        raise RPCError("Invalid response from Engine")
