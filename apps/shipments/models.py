import logging

from django.conf import settings
from django.db import models
from django.core.validators import RegexValidator
from django.contrib.postgres.fields import JSONField
from django.contrib.contenttypes.fields import GenericRelation

from enumfields import Enum
from enumfields import EnumField

from apps.utils import random_id
from apps.jobs.models import JobListener, AsyncJob
from apps.eth.models import EthListener
from .rpc import ShipmentRPCClient

LOG = logging.getLogger('transmission')


class Location(models.Model):
    id = models.CharField(primary_key=True, default=random_id, max_length=36)

    name = models.CharField(max_length=255)
    address_1 = models.CharField(max_length=255, blank=True, null=True)
    address_2 = models.CharField(max_length=255, blank=True, null=True)
    city = models.CharField(max_length=255, blank=True, null=True)
    state = models.CharField(max_length=255, blank=True, null=True)
    country = models.CharField(max_length=255, blank=True, null=True)
    postal_code = models.CharField(max_length=255, blank=True, null=True)

    phone_regex = RegexValidator(regex=r'^(\+\d{1,2}\s)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}',
                                 message="Invalid phone number.")
    phone_number = models.CharField(validators=[phone_regex], max_length=255, blank=True, null=True)
    fax_number = models.CharField(validators=[phone_regex], max_length=255, blank=True, null=True)

    updated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)


class FundingType(Enum):
    SHIP = 0
    CASH = 1
    ETH = 2


class EscrowStatus(Enum):
    CONTRACT_INITIATED = 1
    CONTRACT_SETUP = 2
    CONTRACT_COMMITTED = 3
    CONTRACT_COMPLETED = 4
    CONTRACT_ACCEPTED = 5
    CONTRACT_CANCELED = 6


class ShipmentStatus(Enum):
    PENDING = 0
    INITIATED = 1
    COMPLETED = 2
    CANCELED = 3


class LoadShipment(models.Model):
    id = models.CharField(primary_key=True, default=random_id, max_length=36)

    shipment_id = models.IntegerField(blank=True, null=True)
    funding_type = EnumField(enum=FundingType)

    shipment_amount = models.IntegerField()
    paid_amount = models.IntegerField(default=0)
    paid_tokens = models.DecimalField(max_digits=40, decimal_places=18, default=0)

    shipper = models.CharField(max_length=42)
    carrier = models.CharField(max_length=42)
    moderator = models.CharField(max_length=42, blank=True, null=True)

    escrow_status = EnumField(enum=EscrowStatus, default=EscrowStatus.CONTRACT_INITIATED)
    shipment_status = EnumField(enum=ShipmentStatus, default=ShipmentStatus.PENDING)

    contract_funded = models.BooleanField(default=False)
    shipment_created = models.BooleanField(default=False)
    valid_until = models.IntegerField()
    start_block = models.IntegerField(blank=True, null=True)
    end_block = models.IntegerField(blank=True, null=True)

    escrow_funded = models.BooleanField(default=False)
    shipment_committed_by_carrier = models.BooleanField(default=False)
    commitment_confirmed_date = models.IntegerField(blank=True, null=True)

    shipment_completed_by_carrier = models.BooleanField(default=False)
    shipment_accepted_by_shipper = models.BooleanField(default=False)
    shipment_canceled_by_shipper = models.BooleanField(default=False)
    escrow_paid = models.BooleanField(default=False)


class Shipment(models.Model):
    id = models.CharField(primary_key=True, default=random_id, max_length=36)
    owner_id = models.CharField(null=False, max_length=36)
    load_data = models.OneToOneField(LoadShipment, on_delete=models.CASCADE, null=True)

    storage_credentials_id = models.CharField(null=False, max_length=36)
    vault_id = models.CharField(null=True, max_length=36)
    shipper_wallet_id = models.CharField(null=False, max_length=36)
    carrier_wallet_id = models.CharField(null=False, max_length=36)
    updated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    job_listeners = GenericRelation(JobListener, related_query_name='shipments',
                                    content_type_field='listener_type', object_id_field='listener_id')
    eth_listeners = GenericRelation(EthListener, related_query_name='shipments',
                                    content_type_field='listener_type', object_id_field='listener_id')
    contract_version = models.CharField(null=False, max_length=36)

    class Meta:
        ordering = ('created_at',)

    # Shipment Schema fields
    carrier_scac = models.CharField(max_length=255, blank=True, null=True)
    forwarder_scac = models.CharField(max_length=255, blank=True, null=True)
    nvocc_scac = models.CharField(max_length=255, blank=True, null=True)
    shipper_reference = models.CharField(max_length=255, blank=True, null=True)
    forwarder_reference = models.CharField(max_length=255, blank=True, null=True)
    forwarders_shipper_id = models.CharField(max_length=255, blank=True, null=True)

    ship_from_location = models.ForeignKey(Location, on_delete=models.PROTECT,
                                           related_name='%(class)s_shipments_from', null=True)
    ship_to_location = models.ForeignKey(Location, on_delete=models.PROTECT,
                                         related_name='%(class)s_shipments_to', null=True)
    final_destination_location = models.ForeignKey(Location, on_delete=models.PROTECT,
                                                   related_name='%(class)s_shipments_dest', null=True)

    carrier_instructions = models.CharField(max_length=255, blank=True, null=True)
    pro_number = models.CharField(max_length=255, blank=True, null=True)
    master_bill = models.CharField(max_length=255, blank=True, null=True)
    house_bill = models.CharField(max_length=255, blank=True, null=True)
    subhouse_bill = models.CharField(max_length=255, blank=True, null=True)
    freight_payment_terms = models.CharField(max_length=255, blank=True, null=True)
    vessel_name = models.CharField(max_length=255, blank=True, null=True)
    voyage_number = models.CharField(max_length=255, blank=True, null=True)
    mode = models.CharField(max_length=255, blank=True, null=True)

    number_of_packages = models.IntegerField(blank=True, null=True)
    gross_weight_kgs = models.IntegerField(blank=True, null=True)
    volume_cbms = models.IntegerField(blank=True, null=True)
    container_count = models.IntegerField(blank=True, null=True)
    dimensional_weight = models.IntegerField(blank=True, null=True)
    chargeable_weight = models.IntegerField(blank=True, null=True)

    docs_received_actual = models.DateTimeField(blank=True, null=True)
    docs_approved_actual = models.DateTimeField(blank=True, null=True)
    pickup_appointment_actual = models.DateTimeField(blank=True, null=True)
    pickup_estimated = models.DateTimeField(blank=True, null=True)
    pickup_actual = models.DateTimeField(blank=True, null=True)
    loading_estimated = models.DateTimeField(blank=True, null=True)
    loading_actual = models.DateTimeField(blank=True, null=True)
    departure_estimated = models.DateTimeField(blank=True, null=True)
    departure_actual = models.DateTimeField(blank=True, null=True)
    delivery_appointment_actual = models.DateTimeField(blank=True, null=True)
    arrival_port_estimated = models.DateTimeField(blank=True, null=True)
    arrival_port_actual = models.DateTimeField(blank=True, null=True)
    delivery_estimated = models.DateTimeField(blank=True, null=True)
    delivery_actual = models.DateTimeField(blank=True, null=True)
    last_attempted_delivery_actual = models.DateTimeField(blank=True, null=True)
    cancel_requested_date_actual = models.DateTimeField(blank=True, null=True)
    cancel_confirmed_date_actual = models.DateTimeField(blank=True, null=True)
    customs_filed_date_actual = models.DateTimeField(blank=True, null=True)
    customs_hold_date_actual = models.DateTimeField(blank=True, null=True)
    customs_release_date_actual = models.DateTimeField(blank=True, null=True)

    containerization_type = models.CharField(max_length=255, blank=True, null=True)
    arrival_unlocode = models.CharField(max_length=255, blank=True, null=True)
    final_port_unlocode = models.CharField(max_length=255, blank=True, null=True)
    import_unlocode = models.CharField(max_length=255, blank=True, null=True)
    lading_unlocode = models.CharField(max_length=255, blank=True, null=True)
    origin_unlocode = models.CharField(max_length=255, blank=True, null=True)
    us_routed_export = models.CharField(max_length=255, blank=True, null=True)
    import_customs_mode = models.CharField(max_length=255, blank=True, null=True)
    us_customs_export_port = models.CharField(max_length=255, blank=True, null=True)

    customer_fields = JSONField(blank=True, null=True)

    def get_device_request_url(self):
        return f"{settings.PROFILES_URL}/api/v1/device/?on_shipment={self.vault_id}"

    def update_vault_hash(self, vault_hash):
        async_job = None
        if self.load_data and self.load_data.shipment_id:
            async_job = AsyncJob.rpc_job_for_listener(
                rpc_class=ShipmentRPCClient,
                rpc_method=ShipmentRPCClient.update_vault_hash_transaction,
                rpc_parameters=[self.shipper_wallet_id,
                                self.load_data.shipment_id,
                                '',
                                vault_hash],
                signing_wallet_id=self.shipper_wallet_id,
                listener=self)
        else:
            LOG.error(f'Shipment {self.id} tried to update_vault_hash before load_data.shipment_id was set!')
        return async_job

    # Defaults
    VALID_UNTIL = 24
    FUNDING_TYPE = FundingType.SHIP.value
    SHIPMENT_AMOUNT = 1
