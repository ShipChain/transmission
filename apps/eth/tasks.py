import logging

from celery import shared_task
from celery_once import QueueOnce
from rest_framework.exceptions import APIException
from influxdb_metrics.loader import log_metric


LOG = logging.getLogger('transmission')


@shared_task(base=QueueOnce, once={'graceful': True}, bind=True, autoretry_for=(APIException,),
             retry_backoff=3, retry_backoff_max=60, max_retries=None)
def engine_subscribe(self):
    from apps.eth.rpc import EventRPCClient, RPCError
    log_metric('transmission.info', tags={'method': 'engine_subscribe'})

    try:
        rpc_client = EventRPCClient()
        rpc_client.subscribe()
        LOG.debug('Subscribed to events successfully with the rpc_client.')

    except RPCError as rpc_error:
        # TODO: Metrics/Logs for subscribe failure
        LOG.error('Unable to subscribe to Events: {rpc_error}.')
        raise rpc_error
