import logging

from django.core.management.base import BaseCommand

from django.conf import settings
from shipchain_common.exceptions import RPCError

from apps.eth.models import Transaction, EthAction
from apps.eth.rpc import EventRPCClient
from apps.jobs.models import AsyncJob, JobState
from apps.jobs.tasks import AsyncTask
from apps.shipments.models import Shipment

logger = logging.getLogger()
logger.setLevel(logging.INFO)


class Command(BaseCommand):
    help = 'Moves shipment(s) to etherscan'
    rpc_client = None

    def add_arguments(self, parser):
        parser.add_argument(
            '--shipment_id',
            type=str,
            default=None,
            help='Delete poll instead of closing it',
        )

    def _convert_shipment(self, shipment):
        if not self.rpc_client:
            self.rpc_client = EventRPCClient()
            try:
                self.rpc_client.unsubscribe("LOAD", settings.LOAD_VERSION)
            except RPCError as exc:
                if 'Error: EventSubscription not found' in exc.detail:
                    return
                raise exc
        for async_job in AsyncJob.objects.filter(shipment=shipment):
            try:
                eth_action = EthAction.objects.filter(async_job=async_job).first()
                if eth_action:
                    logger.info(f'Deleting Eth Action: {eth_action.transaction_hash}')
                    eth_action.delete()
                AsyncTask(async_job.id).rerun()
            except Exception as exc:
                print(exc)

    def handle(self, *args, **options):
        if options['shipment_id']:
            shipment = Shipment.objects.filter(id=options['shipment_id']).first()
            if not shipment:
                raise ValueError(f'Invalid shipment id: {options["shipment_id"]} supplied')

            self._convert_shipment(shipment)

        else:
            for shipment in Shipment.objects.all():
                self._convert_shipment(shipment)

        self.rpc_client.subscribe("LOAD", settings.LOAD_VERSION)
