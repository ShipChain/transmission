import logging

import geocoder
from geocoder.keys import mapbox_access_token
from django.conf import settings
from django.contrib.contenttypes.fields import GenericRelation
from django.contrib.gis.db.models import GeometryField
from django.contrib.gis.geos import Point
from django.contrib.postgres.fields import JSONField
from django.core.validators import RegexValidator
from django.db import models
from enumfields import Enum
from enumfields import EnumField
from rest_framework.exceptions import APIException
from rest_framework.status import HTTP_500_INTERNAL_SERVER_ERROR, HTTP_503_SERVICE_UNAVAILABLE
from influxdb_metrics.loader import log_metric

from apps.eth.models import EthListener
from apps.exceptions import ServiceUnavailable
from apps.jobs.models import JobListener, AsyncJob
from apps.utils import random_id
from .rpc import ShipmentRPCClient

LOG = logging.getLogger('transmission')


class Location(models.Model):
    id = models.CharField(primary_key=True, default=random_id, max_length=36)
    owner_id = models.CharField(null=False, max_length=36)

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
    geometry = GeometryField(null=True)

    updated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def get_lat_long_from_address(self):
        LOG.debug(f'Creating lat/long point for location {self.id}')
        log_metric('transmission.info', tags={'method': 'locations.get_lat_long'})
        parsing_address = ''

        if self.address_1:
            parsing_address += self.address_1 + ', '
        if self.address_2:
            parsing_address += self.address_2 + ', '
        if self.city:
            parsing_address += self.city + ', '
        if self.state:
            parsing_address += self.state + ', '
        if self.country:
            parsing_address += self.country + ', '
        if self.postal_code:
            parsing_address += self.postal_code + ', '

        if parsing_address:
            if mapbox_access_token:
                self.geocoder(parsing_address, 'mapbox')
            else:
                self.geocoder(parsing_address, 'google')

    def geocoder(self, parsing_address, method):
        print(method)
        print(mapbox_access_token)
        if method == 'mapbox':
            geocoder_response = geocoder.mapbox(parsing_address)
        elif method == 'google':
            geocoder_response = geocoder.google(parsing_address)

        print(geocoder_response)

        if not geocoder_response.ok:
            if 'OVER_QUERY_LIMIT' in geocoder_response.error:
                log_metric('transmission.errors', tags={'method': f'locations.geocoder', 'code': 'service unavailable',
                                                        'detail': f'error calling {method} geocoder'})
                LOG.debug(f'{method} geocode for address {parsing_address} failed as query limit was reached')
                raise ServiceUnavailable(detail=f'Over Query Limit for {method}',
                                         code=HTTP_503_SERVICE_UNAVAILABLE)

            elif 'No results found' or 'ZERO_RESULTS' in geocoder_response.error:
                log_metric('transmission.errors', tags={'method': f'locations.geocoder', 'code': 'internal server error'
                                                        , 'detail': f'No results returned from {method} geocoder'})
                LOG.debug(f'{method} geocode for address {parsing_address} failed with zero results returned')
                raise APIException(detail='Invalid Location Address',
                                   code=HTTP_500_INTERNAL_SERVER_ERROR)

        else:
            self.geometry = Point(geocoder_response.latlng)


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
                                           related_name='shipments_from', null=True)
    ship_to_location = models.ForeignKey(Location, on_delete=models.PROTECT,
                                         related_name='shipments_to', null=True)
    final_destination_location = models.ForeignKey(Location, on_delete=models.PROTECT,
                                                   related_name='shipments_dest', null=True)

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
    gross_weight_kgs = models.DecimalField(blank=True, null=True, decimal_places=4, max_digits=9)
    volume_cbms = models.DecimalField(blank=True, null=True, decimal_places=4, max_digits=9)
    container_count = models.IntegerField(blank=True, null=True)
    dimensional_weight = models.DecimalField(blank=True, null=True, decimal_places=4, max_digits=9)
    chargeable_weight = models.DecimalField(blank=True, null=True, decimal_places=4, max_digits=9)

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
        LOG.debug(f'Getting device request url for device with vault_id {self.vault_id}')
        return f"{settings.PROFILES_URL}/api/v1/device/?on_shipment={self.vault_id}"

    def update_vault_hash(self, vault_hash):
        LOG.debug(f'Updating vault hash {vault_hash}')
        async_job = None
        if self.load_data and self.load_data.shipment_id:
            LOG.debug(f'Updating for shipment_id {self.load_data.shipment_id}')
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
