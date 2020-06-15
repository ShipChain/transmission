# pylint:disable=invalid-name
import logging

from celery import shared_task
from influxdb_metrics.loader import log_metric
from shipchain_common.exceptions import RPCError

from apps.jobs.models import AsyncActionType
from .rpc import RPCClientFactory
from .models import Shipment

LOG = logging.getLogger('transmission')


@shared_task(bind=True, autoretry_for=(RPCError,),
             retry_backoff=3, retry_backoff_max=60, max_retries=10)
def tracking_data_update(self, shipment_id, payload):
    log_metric('transmission.info', tags={'method': 'shipments_tasks.tracking_data_update',
                                          'module': __name__})
    shipment = Shipment.objects.get(id=shipment_id)

    # TODO: return if shipment is delivered (or otherwise complete)?

    rpc_client = RPCClientFactory.get_client()
    signature = rpc_client.add_tracking_data(shipment.storage_credentials_id,
                                             shipment.shipper_wallet_id,
                                             shipment.vault_id,
                                             payload)
    shipment.set_vault_hash(signature['hash'],
                            rate_limit=shipment.background_data_hash_interval,
                            action_type=AsyncActionType.TRACKING,
                            use_updated_by=False)


@shared_task(bind=True, autoretry_for=(RPCError,),
             retry_backoff=3, retry_backoff_max=60, max_retries=10)
def telemetry_data_update(self, shipment_id, payload):
    log_metric('transmission.info', tags={'method': 'shipments_tasks.telemetry_data_update',
                                          'module': __name__})
    shipment = Shipment.objects.get(id=shipment_id)

    # TODO: return if shipment is delivered (or otherwise complete)?

    rpc_client = RPCClientFactory.get_client()
    signature = rpc_client.add_telemetry_data(shipment.storage_credentials_id,
                                              shipment.shipper_wallet_id,
                                              shipment.vault_id,
                                              payload)
    shipment.set_vault_hash(signature['hash'],
                            rate_limit=shipment.background_data_hash_interval,
                            action_type=AsyncActionType.TELEMETRY,
                            use_updated_by=False)


@shared_task(bind=True)
def gtx_validation_task(self, shipment_id):
    log_metric('transmission.info', tags={'method': 'shipments_tasks.gtx_validation', 'module': __name__})
    shipment = Shipment.objects.get(id=shipment_id)
    shipment.validate_gtx()
    shipment.save()
