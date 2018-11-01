import logging
from datetime import datetime, timedelta
import pytz
from dateutil.parser import parse

import geocoder
from geocoder.keys import mapbox_access_token

import boto3

from django.conf import settings
from django.contrib.contenttypes.fields import GenericRelation
from django.contrib.gis.db.models import GeometryField
from django.contrib.gis.geos import Point
from django.contrib.postgres.fields import JSONField
from django.core.validators import RegexValidator
from django.db import models
from enumfields import Enum
from enumfields import EnumField
from rest_framework.exceptions import ValidationError, Throttled, PermissionDenied
from rest_framework.status import HTTP_200_OK, HTTP_500_INTERNAL_SERVER_ERROR, HTTP_503_SERVICE_UNAVAILABLE
from rest_framework import status
from rest_framework.exceptions import PermissionDenied, APIException
from rest_framework.exceptions import ValidationError, Throttled
from rest_framework.status import HTTP_500_INTERNAL_SERVER_ERROR, HTTP_503_SERVICE_UNAVAILABLE
from geojson import Feature, LineString, Point as Geo_Point
from influxdb_metrics.loader import log_metric

from apps.eth.fields import AddressField, HashField
from apps.eth.models import EthListener
from apps.jobs.models import JobListener, AsyncJob, JobState
from apps.utils import random_id
from .rpc import RPCClientFactory

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
        log_metric('transmission.info', tags={'method': 'locations.get_lat_long', 'module': __name__})
        parsing_address = ''

        if self.address_1:
            parsing_address = self.address_1
        if self.address_2:
            parsing_address += ', ' + self.address_2
        if self.city:
            parsing_address += ', ' + self.city
        if self.state:
            parsing_address += ', ' + self.state
        if self.country:
            parsing_address += ', ' + self.country
        if self.postal_code:
            parsing_address += ', ' + self.postal_code

        if parsing_address:
            if mapbox_access_token:
                self.geocoder(parsing_address, 'mapbox')
            else:
                self.geocoder(parsing_address, 'google')

    def geocoder(self, parsing_address, method):
        if method == 'mapbox':
            geocoder_response = geocoder.mapbox(parsing_address)
        elif method == 'google':
            geocoder_response = geocoder.google(parsing_address)

        if not geocoder_response.ok:
            if 'OVER_QUERY_LIMIT' in geocoder_response.error:
                log_metric('transmission.errors', tags={'method': f'locations.geocoder',
                                                        'code': 'service_unavailable', 'module': __name__,
                                                        'detail': f'error calling {method} geocoder'})
                LOG.debug(f'{method} geocode for address {parsing_address} failed as query limit was reached')
                raise Throttled(detail=f'Over Query Limit for {method}', code=HTTP_503_SERVICE_UNAVAILABLE)

            elif 'No results found' or 'ZERO_RESULTS' in geocoder_response.error:
                log_metric('transmission.errors', tags={'method': f'locations.geocoder',
                                                        'code': 'internal_server_error', 'module': __name__,
                                                        'detail': f'No results returned from {method} geocoder'})
                LOG.debug(f'{method} geocode for address {parsing_address} failed with zero results returned')
                raise ValidationError(detail='Invalid Location Address', code=HTTP_500_INTERNAL_SERVER_ERROR)

        else:
            self.geometry = Point(geocoder_response.latlng)


class Device(models.Model):
    id = models.CharField(primary_key=True, null=False, max_length=36)
    certificate_id = models.CharField(unique=True, null=True, blank=False, max_length=255)

    @staticmethod
    def get_or_create_with_permission(jwt, device_id):
        certificate_id = None
        if settings.PROFILES_ENABLED:
            # Make a request to Profiles /api/v1/devices/{device_id} with the user's JWT
            response = settings.REQUESTS_SESSION.get(f'{settings.PROFILES_URL}/api/v1/device/{device_id}/',
                                                     headers={'Authorization': 'JWT {}'.format(jwt.decode())})
            if response.status_code != HTTP_200_OK:
                raise PermissionDenied("User does not have access to this device in ShipChain Profiles")

        if settings.ENVIRONMENT != 'LOCAL':
            iot = boto3.client('iot')

            try:
                response = iot.list_thing_principals(thingName=device_id)
                if not response['principals']:
                    raise PermissionDenied(f"No certificates found for device {device_id} in AWS IoT")
                for arn in response['principals']:
                    # arn == arn:aws:iot:us-east-1:489745816517:cert/{certificate_id}
                    certificate_id = arn.rsplit('/', 1)[1]
                    break
            except iot.exceptions.ResourceNotFoundException:
                raise PermissionDenied(f"Specified device {device_id} does not exist in AWS IoT")
        return Device.objects.get_or_create(id=device_id, defaults={'certificate_id': certificate_id})[0]


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


class Shipment(models.Model):
    id = models.CharField(primary_key=True, default=random_id, max_length=36)
    owner_id = models.CharField(null=False, max_length=36)

    storage_credentials_id = models.CharField(null=False, max_length=36)
    vault_id = models.CharField(null=True, max_length=36)
    vault_uri = models.CharField(null=True, max_length=255)
    device = models.ForeignKey(Device, on_delete=models.PROTECT, null=True)
    shipper_wallet_id = models.CharField(null=False, max_length=36)
    carrier_wallet_id = models.CharField(null=False, max_length=36)
    moderator_wallet_id = models.CharField(null=True, max_length=36)
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
                listener=self)
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
                listener=self)
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
                listener=self)
        else:
            LOG.info(f'Shipment {self.id} tried to set_vault_uri before contract shipment was created.')
            log_metric('transmission.error', tags={'method': 'shipment.set_vault_uri', 'code': 'call_too_early',
                                                   'module': __name__})
        return async_job

    def set_vault_hash(self, vault_hash, rate_limit=False):
        LOG.debug(f'Updating vault hash {vault_hash}')
        async_job = None
        if self.loadshipment and self.loadshipment.shipment_state is not ShipmentState.NOT_CREATED:
            rpc_client = RPCClientFactory.get_client(self.contract_version)
            job_queryset = AsyncJob.objects.filter(
                joblistener__shipments__id=self.id,
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

                    if (not async_job.delay or async_job.created_at + timedelta(minutes=async_job.delay * 1.2) <
                            datetime.utcnow().replace(tzinfo=pytz.UTC)):
                        # If this is not a delayed job, or this job is after its fire time
                        LOG.warning(f'Pending AsyncJob {async_job.id} is past its scheduled fire time, requeuing')
                        async_job.fire()
            elif rate_limit:
                LOG.debug(f'Shipment {self.id} requested a rate-limited vault hash update')
                LOG.debug(f'No pending vault hash updates for {self.id}, '
                          f'sending one in {settings.VAULT_HASH_RATE_LIMIT} minutes')
                async_job = AsyncJob.rpc_job_for_listener(
                    rpc_method=rpc_client.set_vault_hash_tx,
                    rpc_parameters=[self.shipper_wallet_id,
                                    self.id,
                                    vault_hash],
                    signing_wallet_id=self.shipper_wallet_id,
                    listener=self,
                    delay=settings.VAULT_HASH_RATE_LIMIT)
            else:
                LOG.debug(f'Shipment {self.id} requested a vault hash update')
                async_job = AsyncJob.rpc_job_for_listener(
                    rpc_method=rpc_client.set_vault_hash_tx,
                    rpc_parameters=[self.shipper_wallet_id,
                                    self.id,
                                    vault_hash],
                    signing_wallet_id=self.shipper_wallet_id,
                    listener=self)
        else:
            LOG.info(f'Shipment {self.id} tried to set_vault_hash before contract shipment was created.')
            log_metric('transmission.error', tags={'method': 'shipment.set_vault_hash', 'code': 'call_too_early',
                                                   'module': __name__})
        return async_job

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


class TrackingData(models.Model):
    id = models.CharField(primary_key=True, default=random_id, max_length=36)
    created_at = models.DateTimeField(auto_now_add=True)
    device_id = models.CharField(blank=True, null=True, max_length=36)
    shipment = models.ForeignKey(Shipment, on_delete=models.PROTECT, null=True)
    latitude = models.FloatField(default=None)
    longitude = models.FloatField(default=None)
    altitude = models.FloatField(default=None)
    source = models.CharField(max_length=10)
    uncertainty = models.IntegerField(blank=True, null=True)
    speed = models.IntegerField(blank=True, null=True)
    timestamp = models.CharField(max_length=50)
    geometry = GeometryField(null=True)
    version = models.CharField(max_length=10, null=True, blank=True)

    class Meta:
        ordering = ('created_at',)

    def set_geometry(self):
        self.geometry = Point(self.latitude, self.longitude)

    @property
    def datetime_timestamp(self):
        try:
            return parse(self.timestamp).replace(tzinfo=None)
        except Exception as exception:
            LOG.warning(f'Error Encountered while processing tracking data timestamp: \
            {self.id}. Error message: {exception}')

            raise APIException(detail="Unable to parse tracking data timestamp to datetime object")

    @property
    def timestamp_str(self):
        return self.datetime_timestamp.isoformat()

    @property
    def has_gps(self):
        return True if self.source == 'gps' else False

    @property
    def as_point(self):
        LOG.debug(f'Device tracking as_point.')
        log_metric('transmission.info', tags={'method': 'as_point', 'module': __name__})

        try:
            return Geo_Point((self.longitude, self.latitude))
        except Exception as exception:
            LOG.error(f'Device tracking as_point exception {exception}.')
            log_metric('transmission.error', tags={'method': 'as_point_exception',
                                                   'module': __name__, 'code': 'as_point'})

            raise APIException(detail="Unable to build GeoJSON Point from tracking data")

    @property
    def as_point_feature(self):
        LOG.debug(f'Device tracking as_point.')
        log_metric('transmission.info', tags={'method': 'as_point_feature', 'module': __name__})

        try:
            return Feature(geometry=self.as_point, properties={
                "time": self.timestamp_str,
                "uncertainty": self.uncertainty,
                "has_gps": self.has_gps,
                "source": self.source,
            })
        except Exception as exception:
            LOG.error(f'Device tracking as_point_feature exception {exception}.')
            log_metric('transmission.error', tags={'method': 'as_point_feature_exception',
                                                   'module': __name__, 'code': 'as_point_feature'})

            raise APIException(detail="Unable to build GeoJSON Point Feature from tracking data")

    @staticmethod
    def get_linestring_list(tracking_points):
        linestring = LineString([(point.longitude, point.latitude) for point in tracking_points])
        linestring_timestamps = [point.timestamp_str for point in tracking_points]

        return linestring, linestring_timestamps

    @staticmethod
    def get_linestring_feature(tracking_points):
        try:
            LOG.debug(f'Device tracking get_linestring_list with tracking points {tracking_points}.')
            log_metric('transmission.info', tags={'method': 'get_linestring_list', 'module': __name__})

            linestring, linestring_timestamps = TrackingData.get_linestring_list(tracking_points)
            return Feature(geometry=linestring, properties={"linestringTimestamps": linestring_timestamps})

        except Exception as exception:
            LOG.error(f'Device tracking get_linestring_feature exception {exception}.')
            log_metric('transmission.error', tags={'method': 'get_linestring_feature', 'module': __name__})

            raise APIException(detail="Unable to build GeoJSON LineString Feature from tracking data")
