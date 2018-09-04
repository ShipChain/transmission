# pylint:disable=invalid-name
import importlib

from django.db import transaction
from django.core.cache import cache
from celery import shared_task

from apps.rpc_client import RPCError


@shared_task(bind=True, autoretry_for=(Exception,),
             retry_backoff=3, retry_backoff_max=60, max_retries=0)  # TODO: enable retries
def async_job_fire(self, async_job_id):
    from .models import AsyncJob, JobState

    print(f'AsyncJob {async_job_id} firing!')
    async_job = AsyncJob.objects.get(id=async_job_id)

    if async_job.state == JobState.PENDING:
        try:
            with cache.lock(async_job.parameters['signing_wallet_id']):  # Only one concurrent tx per wallet
                # Find which RPC module/class to import
                module_name, rpc_class_name = async_job.parameters['rpc_class'].rsplit('.', 1)
                module = importlib.import_module(module_name)
                rpc_client = getattr(module, rpc_class_name)()

                # Generate transaction via RPC
                unsigned_tx = _generic_get_transaction(rpc_client, async_job)

                # Sign tx via RPC
                signed_tx, eth_action = _sign_transaction(rpc_client, async_job, unsigned_tx)

                # Send tx via RPC
                _send_transaction(rpc_client, async_job, signed_tx, eth_action)

                # TODO: Metrics/Logs for success
                print("Eth TX Submitted via AsyncJob")
        except RPCError as rpc_error:
            # TODO: Metrics/Logs for failure
            print(f"Unexpected RPC error: {rpc_error}")
            raise self.retry(exc=rpc_error)


def _generic_get_transaction(rpc_client, async_job):
    if async_job.parameters['rpc_method'] == 'create_shipment_transaction':
        contract_version, unsigned_tx = getattr(rpc_client, async_job.parameters['rpc_method'])(
            *async_job.parameters['rpc_parameters'])
        for shipment in async_job.listeners.filter(Model='shipments.Shipment'):
            shipment.contract_version = contract_version
            shipment.save()
    else:
        unsigned_tx = getattr(rpc_client, async_job.parameters['rpc_method'])(
            *async_job.parameters['rpc_parameters'])
    return unsigned_tx


def _sign_transaction(rpc_client, async_job, unsigned_tx):
    from apps.eth.models import EthAction, Transaction

    signed_tx, hash_tx = getattr(rpc_client, 'sign_transaction')(async_job.parameters['signing_wallet_id'],
                                                                 unsigned_tx)
    async_job.parameters['signed_tx'] = signed_tx

    # Create EthAction so this Job's Listeners can also listen to Events posted for the TransactionHash
    with transaction.atomic():
        eth_action, _ = EthAction.objects.update_or_create(transaction_hash=hash_tx, defaults={
            'async_job': async_job
        })
        for job_listener in async_job.joblistener_set.all():
            eth_action.ethlistener_set.create(listener=job_listener.listener)

        eth_action.transaction = Transaction.from_unsigned_tx(unsigned_tx)
        eth_action.transaction.hash = hash_tx
        eth_action.transaction.save()
        eth_action.save()

    return signed_tx, eth_action


def _send_transaction(rpc_client, async_job, signed_tx, eth_action):
    from .models import JobState
    from apps.eth.models import TransactionReceipt

    receipt = getattr(rpc_client, 'send_transaction')(signed_tx, async_job.get_callback_url())
    with transaction.atomic():
        eth_action.transactionreceipt = TransactionReceipt.from_eth_receipt(receipt)
        eth_action.transactionreceipt.save()

        async_job.state = JobState.RUNNING
        async_job.save()
