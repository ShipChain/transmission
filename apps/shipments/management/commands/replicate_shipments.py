import logging
import sys
import time

from django.conf import settings
from django.core.management.base import BaseCommand
from shipchain_common.exceptions import RPCError

from apps.eth.models import EthAction
from apps.eth.rpc import EventRPCClient
from apps.jobs.models import AsyncJob, Message
from apps.jobs.tasks import AsyncTask
from apps.shipments.models import Shipment

logger = logging.getLogger('transmission')
logger.setLevel(settings.LOG_LEVEL)


class Command(BaseCommand):
    help = 'Replicate shipment related transactions to the sidechain.'
    rpc_client = None
    successfull_shipments = []
    unsuccessfull_shipments = []
    async_job = None

    def add_arguments(self, parser):
        parser.add_argument(
            '--shipment_id',
            type=str,
            default=None,
            help='Replicate specific shipment instead of all of them.',
        )

    def _replicate_shipment(self, shipment):
        self.successfull_shipments.append(shipment.id)
        if not self.rpc_client:
            self.rpc_client = EventRPCClient()
            try:
                self.rpc_client.unsubscribe("LOAD", settings.LOAD_VERSION)
            except RPCError as exc:
                if 'Error: EventSubscription not found' not in exc.detail:
                    raise exc

        for async_job in AsyncJob.objects.filter(shipment=shipment):
            try:
                eth_action = EthAction.objects.filter(async_job=async_job).first()
                if eth_action:
                    logger.info(f'Deleting Eth Action: {eth_action.transaction_hash}')
                    eth_action.delete()
                AsyncTask(async_job.id).rerun()
                self.async_job = async_job

            # pylint:disable=broad-except
            except Exception as exc:
                if shipment.id in self.successfull_shipments:
                    self.successfull_shipments.remove(shipment.id)
                    self.unsuccessfull_shipments.append(shipment.id)
                logger.error(exc)

    def _resubscribe(self):
        if not self.async_job:
            logger.warning('Unable to find last blockheight to subscribe to. '
                           'Need to manually subscribe to latest blockheight')
            return

        message = Message.objects.filter(async_job=self.async_job).last()
        if "blockNumber" not in message.body:
            time.sleep(15)
            message = Message.objects.filter(async_job=self.async_job).last()
        if "blockNumber" in message.body:
            self.rpc_client.subscribe("LOAD", settings.LOAD_VERSION, blockheight=message.body["blockNumber"])
        else:
            logger.warning('Unable to find last blockheight to subscribe to. '
                           'Need to manually subscribe to latest blockheight')

    def handle(self, *args, **options):
        if options['shipment_id']:
            shipment = Shipment.objects.filter(id=options['shipment_id']).first()
            if not shipment:
                logger.error(f'Invalid shipment id: {options["shipment_id"]} supplied')
                sys.exit()

            self._replicate_shipment(shipment)

        else:
            shipments = Shipment.objects.all()
            logger.info(f'Shipments to replicate: {shipments.count()}')
            for shipment in shipments:
                self._replicate_shipment(shipment)

        logger.info(f'Successful shipments count: {len(self.successfull_shipments)}')
        logger.debug(f'Successful shipments: {self.successfull_shipments}')

        logger.warning(f'Unsuccessful shipments count: {len(self.unsuccessfull_shipments)}')
        logger.warning(f'Unsuccessful shipments: {self.unsuccessfull_shipments}')
        self._resubscribe()
