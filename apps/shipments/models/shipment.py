"""
Copyright 2019 ShipChain, Inc.

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""
import logging
from datetime import datetime, timedelta, timezone

import hashlib
import pytz
from django.conf import settings
from django.contrib.postgres.fields import JSONField, ArrayField
from django.core.validators import RegexValidator, MinValueValidator
from django.db import models
from django_fsm import FSMIntegerField, transition
from enumfields import Enum, EnumIntegerField
from enumfields import EnumField
from influxdb_metrics.loader import log_metric
from rest_framework.exceptions import PermissionDenied
from shipchain_common.utils import random_id

from apps.eth.fields import AddressField, HashField
from apps.jobs.models import AsyncJob, JobState
from apps.shipments.models import Device, Location
from apps.simple_history import TxmHistoricalRecords, AnonymousHistoricalMixin
from ..rpc import RPCClientFactory

LOG = logging.getLogger('transmission')

# pylint: disable=too-many-branches


class FundingType(Enum):
    NO_FUNDING = 0
    SHIP = 1
    ETHER = 2


class ShipmentState(Enum):
    NOT_CREATED = 0
    CREATED = 1
    IN_PROGRESS = 2
    COMPLETE = 3
    CANCELED = 4


class EscrowState(Enum):
    NOT_CREATED = 0
    CREATED = 1
    FUNDED = 2
    RELEASED = 3
    REFUNDED = 4
    WITHDRAWN = 5


class TransitState(Enum):
    AWAITING_PICKUP = 10
    IN_TRANSIT = 20
    AWAITING_DELIVERY = 30
    DELIVERED = 40

    @classmethod
    def choices(cls):
        return tuple((m.value, m.name) for m in cls)


class ExceptionType(Enum):
    NONE = 0
    CUSTOMS_HOLD = 1
    DOCUMENTATION_ERROR = 2


class Shipment(AnonymousHistoricalMixin, models.Model):
    id = models.CharField(primary_key=True, default=random_id, max_length=36)
    owner_id = models.CharField(null=False, max_length=36)
    assignee_id = models.UUIDField(null=True)

    storage_credentials_id = models.CharField(null=False, max_length=36)
    vault_id = models.CharField(null=True, max_length=36)
    vault_uri = models.CharField(null=True, max_length=255)
    device = models.OneToOneField(Device, on_delete=models.PROTECT, null=True)
    shipper_wallet_id = models.CharField(null=False, max_length=36)
    carrier_wallet_id = models.CharField(null=False, max_length=36)
    moderator_wallet_id = models.CharField(null=True, max_length=36)
    updated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    contract_version = models.CharField(null=False, max_length=36)
    background_data_hash_interval = models.IntegerField(validators=[MinValueValidator(0)],
                                                        default=settings.DEFAULT_BACKGROUND_DATA_HASH_INTERVAL)
    manual_update_hash_interval = models.IntegerField(validators=[MinValueValidator(0)],
                                                      default=settings.DEFAULT_MANUAL_UPDATE_HASH_INTERVAL)

    updated_by = models.CharField(null=True, max_length=36)

    class Meta:
        ordering = ('created_at',)

    # Protected Fields
    state = FSMIntegerField(default=TransitState.AWAITING_PICKUP.value, protected=True)
    delayed = models.BooleanField(default=False, editable=False)
    expected_delay_hours = models.IntegerField(default=0, editable=False)
    exception = EnumIntegerField(enum=ExceptionType, default=ExceptionType.NONE)

    # Shipment Schema fields
    carriers_scac = models.CharField(max_length=255, blank=True, null=True)
    forwarders_scac = models.CharField(max_length=255, blank=True, null=True)
    nvocc_scac = models.CharField(max_length=255, blank=True, null=True)
    shippers_reference = models.CharField(max_length=255, blank=True, null=True)
    forwarders_reference = models.CharField(max_length=255, blank=True, null=True)
    forwarders_shipper_id = models.CharField(max_length=255, blank=True, null=True)

    ship_from_location = models.OneToOneField(Location, on_delete=models.PROTECT,
                                              related_name='shipment_from', null=True)
    ship_to_location = models.OneToOneField(Location, on_delete=models.PROTECT,
                                            related_name='shipment_to', null=True)
    final_destination_location = models.OneToOneField(Location, on_delete=models.PROTECT,
                                                      related_name='shipment_dest', null=True)
    bill_to_location = models.OneToOneField(Location, on_delete=models.PROTECT,
                                            related_name='shipment_bill', null=True)

    carriers_instructions = models.CharField(max_length=255, blank=True, null=True)
    special_instructions = models.CharField(max_length=255, blank=True, null=True)
    pro_number = models.CharField(max_length=255, blank=True, null=True)
    bill_master = models.CharField(max_length=255, blank=True, null=True)
    bill_house = models.CharField(max_length=255, blank=True, null=True)
    bill_subhouse = models.CharField(max_length=255, blank=True, null=True)
    payment_terms = models.CharField(max_length=255, blank=True, null=True)
    vessel_name = models.CharField(max_length=255, blank=True, null=True)
    voyage_number = models.CharField(max_length=255, blank=True, null=True)
    mode_of_transport_code = models.CharField(max_length=255, blank=True, null=True)

    package_qty = models.IntegerField(blank=True, null=True)
    weight_gross = models.DecimalField(blank=True, null=True, decimal_places=4, max_digits=9)
    volume = models.DecimalField(blank=True, null=True, decimal_places=4, max_digits=9)
    container_qty = models.IntegerField(blank=True, null=True)
    weight_dim = models.DecimalField(blank=True, null=True, decimal_places=4, max_digits=9)
    weight_chargeable = models.DecimalField(blank=True, null=True, decimal_places=4, max_digits=9)

    docs_received_act = models.DateTimeField(blank=True, null=True)
    docs_approved_act = models.DateTimeField(blank=True, null=True)
    pickup_appt = models.DateTimeField(blank=True, null=True)
    pickup_est = models.DateTimeField(blank=True, null=True)
    pickup_act = models.DateTimeField(blank=True, null=True, editable=False)
    loading_est = models.DateTimeField(blank=True, null=True)
    loading_act = models.DateTimeField(blank=True, null=True)
    departure_est = models.DateTimeField(blank=True, null=True)
    departure_act = models.DateTimeField(blank=True, null=True)
    delivery_appt_act = models.DateTimeField(blank=True, null=True)
    port_arrival_est = models.DateTimeField(blank=True, null=True)
    port_arrival_act = models.DateTimeField(blank=True, null=True, editable=False)
    delivery_est = models.DateTimeField(blank=True, null=True)
    delivery_act = models.DateTimeField(blank=True, null=True, editable=False)
    delivery_attempt = models.DateTimeField(blank=True, null=True)
    cancel_requested_date_act = models.DateTimeField(blank=True, null=True)
    cancel_confirmed_date_act = models.DateTimeField(blank=True, null=True)
    customs_filed_date_act = models.DateTimeField(blank=True, null=True)
    customs_hold_date_act = models.DateTimeField(blank=True, null=True)
    customs_release_date_act = models.DateTimeField(blank=True, null=True)

    container_type = models.CharField(max_length=255, blank=True, null=True)
    port_arrival_locode = models.CharField(max_length=255, blank=True, null=True)
    final_port_locode = models.CharField(max_length=255, blank=True, null=True)
    import_locode = models.CharField(max_length=255, blank=True, null=True)
    lading_locode = models.CharField(max_length=255, blank=True, null=True)
    origin_locode = models.CharField(max_length=255, blank=True, null=True)
    us_routed = models.NullBooleanField()
    import_customs_mode = models.CharField(max_length=255, blank=True, null=True)
    us_export_port = models.CharField(max_length=255, blank=True, null=True)
    version = models.CharField(max_length=255, blank=False, null=False, default=settings.SHIPMENT_SCHEMA_VERSION)

    trailer_number = models.CharField(max_length=255, blank=True, null=True)
    seal_number = models.CharField(max_length=255, blank=True, null=True)
    is_master_bol = models.NullBooleanField()

    nmfc_regex = RegexValidator(regex=r'^1[015]0$|^1[27]5$|^2[05]0$|^[345]00$|^[567]0$|^[568]5$|^92\.5$|^77\.5$',
                                message="Invalid nmfc class number.")
    nmfc_class = models.CharField(validators=[nmfc_regex], max_length=4, blank=True, null=True)

    is_hazmat = models.NullBooleanField()

    gtx_required = models.BooleanField(default=False)
    asset_physical_id = models.CharField(null=True, max_length=255)
    asset_custodian_id = models.CharField(null=True, max_length=36)

    geofences = ArrayField(models.CharField(null=True, max_length=36), blank=True, null=True)

    customer_fields = JSONField(blank=True, null=True)

    aftership_tracking = models.CharField(null=True, max_length=100)

    # Model's history tracking definition
    history = TxmHistoricalRecords()

    def get_device_request_url(self):
        LOG.debug(f'Getting device request url for device with vault_id {self.vault_id}')
        return f"{settings.PROFILES_URL}/api/v1/device/?on_shipment={self.vault_id}"

    def set_carrier(self):
        LOG.debug(f'Updating carrier {self.carrier_wallet_id}')
        async_job = None
        if self.loadshipment and self.loadshipment.shipment_state is not ShipmentState.NOT_CREATED:
            rpc_client = RPCClientFactory.get_client(self.contract_version)
            LOG.debug(f'Shipment {self.id} requested a carrier update')
            async_job = AsyncJob.rpc_job_for_listener(
                rpc_method=rpc_client.set_carrier_tx,
                rpc_parameters=[self.shipper_wallet_id,
                                self.id,
                                self.carrier_wallet_id],
                signing_wallet_id=self.shipper_wallet_id,
                shipment=self)
        else:
            LOG.info(f'Shipment {self.id} tried to set_carrier before contract shipment was created.')
            log_metric('transmission.error', tags={'method': 'shipment.set_carrier', 'code': 'call_too_early',
                                                   'module': __name__})
        return async_job

    def set_moderator(self):
        LOG.debug(f'Updating moderator {self.moderator_wallet_id}')
        async_job = None
        if self.loadshipment and self.loadshipment.shipment_state is not ShipmentState.NOT_CREATED:
            rpc_client = RPCClientFactory.get_client(self.contract_version)
            LOG.debug(f'Shipment {self.id} requested a carrier update')
            async_job = AsyncJob.rpc_job_for_listener(
                rpc_method=rpc_client.set_moderator_tx,
                rpc_parameters=[self.shipper_wallet_id,
                                self.id,
                                self.moderator_wallet_id],
                signing_wallet_id=self.shipper_wallet_id,
                shipment=self)
        else:
            LOG.info(f'Shipment {self.id} tried to set_moderator before contract shipment was created.')
            log_metric('transmission.error', tags={'method': 'shipment.set_moderator', 'code': 'call_too_early',
                                                   'module': __name__})
        return async_job

    def set_vault_uri(self, vault_uri):
        LOG.debug(f'Updating vault uri {vault_uri}')
        async_job = None
        if self.loadshipment and self.loadshipment.shipment_state is not ShipmentState.NOT_CREATED:
            rpc_client = RPCClientFactory.get_client(self.contract_version)
            LOG.debug(f'Shipment {self.id} requested a vault uri update')
            async_job = AsyncJob.rpc_job_for_listener(
                rpc_method=rpc_client.set_vault_uri_tx,
                rpc_parameters=[self.shipper_wallet_id,
                                self.id,
                                vault_uri],
                signing_wallet_id=self.shipper_wallet_id,
                shipment=self)
        else:
            LOG.info(f'Shipment {self.id} tried to set_vault_uri before contract shipment was created.')
            log_metric('transmission.error', tags={'method': 'shipment.set_vault_uri', 'code': 'call_too_early',
                                                   'module': __name__})
        return async_job

    def set_vault_hash(self, vault_hash, action_type, rate_limit=None, use_updated_by=True):
        LOG.debug(f'Updating vault hash {vault_hash}')
        async_job = None
        if self.loadshipment and self.loadshipment.shipment_state is not ShipmentState.NOT_CREATED:
            if rate_limit is None:
                rate_limit = self.manual_update_hash_interval

            rpc_client = RPCClientFactory.get_client(self.contract_version)
            job_queryset = AsyncJob.objects.filter(
                shipment__id=self.id,
                state=JobState.PENDING,
                parameters__rpc_method=rpc_client.set_vault_hash_tx.__name__,
                parameters__signing_wallet_id=self.shipper_wallet_id,
            )
            if job_queryset.count():
                # Update vault hash for all current queued jobs
                for async_job in job_queryset.all():
                    LOG.debug(f'Shipment {self.id} found a pending vault hash update {async_job.id}, '
                              f'updating its parameters with new hash')
                    async_job.parameters['rpc_parameters'] = [
                        self.shipper_wallet_id,
                        self.id,
                        vault_hash
                    ]
                    async_job.save()
                    async_job.actions.create(action_type=action_type,
                                             vault_hash=vault_hash,
                                             user_id=self.updated_by if use_updated_by else None)

                    if (not async_job.delay or async_job.created_at + timedelta(minutes=async_job.delay * 1.2) <
                            datetime.utcnow().replace(tzinfo=pytz.UTC)):
                        # If this is not a delayed job, or this job is after its fire time
                        LOG.warning(f'Pending AsyncJob {async_job.id} is past its scheduled fire time, requeuing')
                        async_job.fire()
            elif rate_limit:
                LOG.debug(f'Shipment {self.id} requested a rate-limited vault hash update')
                LOG.debug(f'No pending vault hash updates for {self.id}, '
                          f'sending one in {rate_limit} minutes')
                async_job = AsyncJob.rpc_job_for_listener(
                    rpc_method=rpc_client.set_vault_hash_tx,
                    rpc_parameters=[self.shipper_wallet_id,
                                    self.id,
                                    vault_hash],
                    signing_wallet_id=self.shipper_wallet_id,
                    shipment=self,
                    delay=rate_limit)
                async_job.actions.create(action_type=action_type,
                                         vault_hash=vault_hash,
                                         user_id=self.updated_by if use_updated_by else None)
            else:
                LOG.debug(f'Shipment {self.id} requested a vault hash update')
                async_job = AsyncJob.rpc_job_for_listener(
                    rpc_method=rpc_client.set_vault_hash_tx,
                    rpc_parameters=[self.shipper_wallet_id,
                                    self.id,
                                    vault_hash],
                    signing_wallet_id=self.shipper_wallet_id,
                    shipment=self)
                async_job.actions.create(action_type=action_type,
                                         vault_hash=vault_hash,
                                         user_id=self.updated_by if use_updated_by else None)
        else:
            LOG.info(f'Shipment {self.id} tried to set_vault_hash before contract shipment was created.')
            log_metric('transmission.error', tags={'method': 'shipment.set_vault_hash', 'code': 'call_too_early',
                                                   'module': __name__})
        return async_job

    # State transitions
    @transition(field=state, source=TransitState.AWAITING_PICKUP.value, target=TransitState.IN_TRANSIT.value)
    def pick_up(self, document_id=None, asset_physical_id=None, **kwargs):
        if document_id:
            # TODO: Validate that ID is a BOL Document?
            pass

        if self.gtx_required and not asset_physical_id:
            raise PermissionDenied('In order to proceed with this shipment pick up, '
                                   'you need to provide a value for the field [Shipment.asset_physical_id].')

        if asset_physical_id:
            self.asset_physical_id = hashlib.sha256(asset_physical_id.encode()).hexdigest()

        self.pickup_act = datetime.now(timezone.utc)  # TODO: pull from action parameters?

    @transition(field=state, source=TransitState.IN_TRANSIT.value, target=TransitState.AWAITING_DELIVERY.value)
    def arrival(self, tracking_data=None, **kwargs):
        if tracking_data:
            # TODO: Validate that tracking update is within bbox around delivery location?
            pass
        self.port_arrival_act = datetime.now(timezone.utc)

    @transition(field=state, source=TransitState.AWAITING_DELIVERY.value, target=TransitState.DELIVERED.value)
    def drop_off(self, document_id=None, raw_asset_physical_id=None, **kwargs):
        if document_id:
            # TODO: Validate that ID is a BOL Document?
            pass

        if self.asset_physical_id:
            # Validate opaque physical ID (SHA256)
            if not raw_asset_physical_id or (self.asset_physical_id !=
                                             hashlib.sha256(raw_asset_physical_id.encode()).hexdigest()):
                raise PermissionDenied(f"Hash of asset tag does not match value "
                                       f"specified in Shipment.asset_physical_id")

        self.delivery_act = datetime.now(timezone.utc)  # TODO: pull from action parameters?

    # Defaults
    FUNDING_TYPE = FundingType.NO_FUNDING.value
    SHIPMENT_AMOUNT = 0


class LoadShipment(models.Model):
    shipment = models.OneToOneField(Shipment, primary_key=True, on_delete=models.CASCADE)

    # Shipment.Data
    shipper = AddressField()
    carrier = AddressField()
    moderator = AddressField()
    shipment_state = EnumField(enum=ShipmentState, default=ShipmentState.NOT_CREATED)

    # Escrow.Data
    contracted_amount = models.IntegerField(default=0)
    funded_amount = models.IntegerField(default=0)
    created_at = models.IntegerField(default=0)
    funding_type = EnumField(enum=FundingType, default=FundingType.NO_FUNDING)
    escrow_state = EnumField(enum=EscrowState, default=EscrowState.NOT_CREATED)
    refund_address = AddressField()

    # Vault.Data
    vault_hash = HashField()
    vault_uri = models.CharField(max_length=255, blank=True)
