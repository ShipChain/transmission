import logging

from celery import shared_task
from celery_once import QueueOnce
from django.conf import settings
from influxdb_metrics.loader import log_metric
from rest_framework.exceptions import APIException

LOG = logging.getLogger('transmission')


def engine_subscribe_generic(project, version, events=None):
    from apps.eth.rpc import EventRPCClient, RPCError
    log_metric('transmission.info', tags={'method': f'eth.engine_subscribe_{project.lower()}',
                                          'module': __name__})
    try:
        rpc_client = EventRPCClient()
        rpc_client.subscribe(project=project, version=version, events=events)
        LOG.debug(f'Subscribed to {project} events for version {version} successfully with the rpc_client.')

    except RPCError as rpc_error:
        log_metric('transmission.info', tags={'method': f'eth.engine_subscribe_{project.lower()}', 'code': 'RPCError',
                                              'module': __name__})
        LOG.error(f'Unable to subscribe to {project}, for version {version}, Events: {rpc_error}.')
        raise rpc_error


@shared_task(base=QueueOnce, once={'graceful': True}, bind=True, autoretry_for=(APIException,),
             retry_backoff=3, retry_backoff_max=60, max_retries=None)
def engine_subscribe_load(self):
    engine_subscribe_generic("LOAD", settings.LOAD_VERSION)


@shared_task(base=QueueOnce, once={'graceful': True}, bind=True, autoretry_for=(APIException,),
             retry_backoff=3, retry_backoff_max=60, max_retries=None)
def engine_subscribe_token(self):
    engine_subscribe_generic("ShipToken", settings.SHIPTOKEN_VERSION, ["Transfer"])
