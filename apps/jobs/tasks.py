# pylint:disable=invalid-name
import importlib
import logging
import random

from celery import shared_task
from django.core.cache import cache
from django.db import transaction
from django.conf import settings
from influxdb_metrics.loader import log_metric

from apps.rpc_client import RPCError
from .exceptions import WalletInUseException, TransactionCollisionException

LOG = logging.getLogger('transmission')


class AsyncTask:
    def __init__(self, async_job_id):
        from .models import AsyncJob
        self.async_job = AsyncJob.objects.get(id=async_job_id)

        self.wallet_id = self.async_job.parameters['signing_wallet_id']

        # Find which RPC module/class to import
        module_name, rpc_class_name = self.async_job.parameters['rpc_class'].rsplit('.', 1)
        module = importlib.import_module(module_name)
        self.rpc_client = getattr(module, rpc_class_name)()

    def run(self):
        log_metric('transmission.info', tags={'method': 'run'})
        from .models import JobState
        if self.async_job.state not in (JobState.RUNNING, JobState.COMPLETE):
            LOG.debug(f'Job {self.async_job.id} running with status {self.async_job.state}')
            wallet_id = self.async_job.parameters['signing_wallet_id']
            wallet_lock = cache.lock(self.async_job.parameters['signing_wallet_id'], timeout=settings.WALLET_TIMEOUT)
            if wallet_lock.acquire(blocking=False):  # Only one concurrent tx per wallet
                # Generate, sign, and send tx via RPC
                try:
                    LOG.debug(f'Lock on {wallet_id} acquired, attempting to send transaction')
                    self.async_job.wallet_lock_token = wallet_lock.local.token.decode()
                    self._send_transaction(*self._sign_transaction(self._get_transaction()))
                except Exception as e:
                    # If there was an exception, release the lock and re-raise
                    wallet_lock.release()
                    raise e
                LOG.debug(f'Transaction submitted via AsyncJob {self.async_job.id}')
                log_metric('transmission.info', tags={'method': 'async_job_fire'})
            else:  # Could not lock on wallet, transaction already in progress
                raise WalletInUseException(f'Wallet {wallet_id} is currently already in use.')

    def _get_transaction(self):
        LOG.debug(f'Getting transaction for job {self.async_job.id}, {self.async_job.parameters["rpc_method"]}')
        log_metric('transmission.info', tags={'method': '_get_transaction'})
        if self.async_job.parameters['rpc_method'] == 'create_shipment_transaction':
            contract_version, unsigned_tx = getattr(self.rpc_client, self.async_job.parameters['rpc_method'])(
                *self.async_job.parameters['rpc_parameters'])
            for shipment in self.async_job.listeners.filter(Model='shipments.Shipment'):
                shipment.contract_version = contract_version
                shipment.save()
        else:
            unsigned_tx = getattr(self.rpc_client, self.async_job.parameters['rpc_method'])(
                *self.async_job.parameters['rpc_parameters'])
        return unsigned_tx

    def _sign_transaction(self, unsigned_tx):
        LOG.debug(f'Signing transaction for job {self.async_job.id}')
        log_metric('transmission.info', tags={'method': '_sign_transaction'})
        from apps.eth.models import EthAction, Transaction

        signed_tx, hash_tx = getattr(self.rpc_client, 'sign_transaction')(
            self.async_job.parameters['signing_wallet_id'], unsigned_tx)
        self.async_job.parameters['signed_tx'] = signed_tx

        # Create EthAction so this Job's Listeners can also listen to Events posted for the TransactionHash
        with transaction.atomic():
            eth_action, created = EthAction.objects.get_or_create(transaction_hash=hash_tx, defaults={
                'async_job': self.async_job
            })
            if created:
                LOG.debug(f'Created new EthAction {eth_action.id}')
                for job_listener in self.async_job.joblistener_set.all():
                    eth_action.ethlistener_set.create(listener=job_listener.listener)

                eth_action.transaction = Transaction.from_unsigned_tx(unsigned_tx)
                eth_action.transaction.hash = hash_tx
                eth_action.transaction.save()
                eth_action.save()
            else:
                # There is already a transaction with this transaction hash - retry later (get another nonce)
                raise TransactionCollisionException(f'A transaction with the hash {hash_tx} is already in progress.')

        return signed_tx, eth_action

    def _send_transaction(self, signed_tx, eth_action):
        from .models import JobState
        from apps.eth.models import TransactionReceipt
        LOG.debug(f'Sending transaction for job {self.async_job.id}, hash {eth_action.transaction_hash}')
        log_metric('transmission.info', tags={'method': '_send_transaction'})

        receipt = getattr(self.rpc_client, 'send_transaction')(signed_tx, self.async_job.get_callback_url())
        with transaction.atomic():
            eth_action.transactionreceipt = TransactionReceipt.from_eth_receipt(receipt)
            eth_action.transactionreceipt.save()

            self.async_job.state = JobState.RUNNING
            self.async_job.save()


@shared_task(bind=True, autoretry_for=(RPCError,),
             retry_backoff=3, retry_backoff_max=60, max_retries=10)
def async_job_fire(self, async_job_id):
    LOG.debug(f'AsyncJob {async_job_id} firing!')
    log_metric('transmission.info', tags={'method': 'async_job_fire'})

    task = AsyncTask(async_job_id)
    try:
        task.run()
    except WalletInUseException as wallet_ex:
        LOG.info(f"AsyncJob can't be processed yet ({async_job_id}): {wallet_ex}")
        raise self.retry(exc=wallet_ex, countdown=settings.CELERY_WALLET_RETRY * random.uniform(0.5, 1.5))  # Jitter
    except TransactionCollisionException as tx_ex:
        LOG.info(f"AsyncJob can't be processed yet ({async_job_id}): {tx_ex}")
        raise self.retry(exc=tx_ex, countdown=settings.CELERY_TXHASH_RETRY * random.uniform(0.5, 1.5))  # Jitter
    except RPCError as rpc_error:
        LOG.error(f"AsyncJob Exception ({async_job_id}): {rpc_error}")
        raise rpc_error
