from apps.eth.models import Event
from apps.rpc_client import RPCClient, RPCError


class EventRPCClient(RPCClient):

    def subscribe(self, url=Event.get_event_subscription_url(), project="LOAD", interval=5000, events=None):

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
