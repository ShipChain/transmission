# pylint:disable=invalid-name
import logging

from celery import shared_task
from influxdb_metrics.loader import log_metric

from apps.rpc_client import RPCError
from .rpc import ShipmentRPCClient
from .models import Shipment

LOG = logging.getLogger('transmission')


@shared_task(bind=True, autoretry_for=(RPCError,),
             retry_backoff=3, retry_backoff_max=60, max_retries=10)
def tracking_data_update(self, shipment_id, payload):
    log_metric('transmission.info', tags={'method': 'shipments.tasks.tracking_data_update'})
    shipment = Shipment.objects.get(id=shipment_id)

    rpc_client = ShipmentRPCClient()
    vault_hash = rpc_client.add_tracking_data(shipment.storage_credentials_id,
                                              shipment.shipper_wallet_id,
                                              shipment.vault_id,
                                              payload)
    shipment.update_vault_hash(vault_hash, rate_limit=True)
