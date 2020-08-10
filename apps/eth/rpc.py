import logging

from influxdb_metrics.loader import log_metric
from shipchain_common.exceptions import RPCError
from shipchain_common.rpc import RPCClient

from apps.eth.models import Event


LOG = logging.getLogger('transmission')


class EventRPCClient(RPCClient):

    # pylint:disable=too-many-arguments
    def subscribe(self, project, version, url=Event.get_event_subscription_url(), interval=5000, events=None):
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

    def unsubscribe(self, project, version, url=Event.get_event_subscription_url()):
        LOG.debug(f'Event unsubscription with url {url}.')
        log_metric('transmission.info', tags={'method': 'event_rpcclient.subscribe',
                                              'module': __name__})

        result = self.call('event.unsubscribe', {
            "url": url,
            "project": project,
            "version": version
        })

        if 'success' in result and result['success']:
            if 'subscription' in result:
                return

        log_metric('transmission.error', tags={'method': 'event_rpcclient.unsubscribe', 'code': 'RPCError',
                                               'module': __name__})
        raise RPCError("Invalid response from Engine")
