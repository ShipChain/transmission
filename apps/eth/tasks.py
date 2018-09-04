from celery import shared_task
from celery_once import QueueOnce


@shared_task(base=QueueOnce, once={'graceful': True}, bind=True, autoretry_for=(Exception,),
             retry_backoff=3, retry_backoff_max=60, max_retries=None)
def engine_subscribe(self):
    from apps.eth.rpc import EventRPCClient, RPCError

    try:
        rpc_client = EventRPCClient()
        rpc_client.subscribe()
        # TODO: Metrics/Logs for subscribe successful
        print("Subscribed to Events")

    except RPCError as rpc_error:
        # TODO: Metrics/Logs for subscribe failure
        print(f"Unable to subscribe to Events: {rpc_error}")
        raise self.retry(exc=rpc_error)
