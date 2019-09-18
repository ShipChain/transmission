import json
import logging
from collections import OrderedDict
from datetime import datetime, timezone, timedelta
from functools import partial

import boto3
from botocore.exceptions import ClientError, BotoCoreError
from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from dateutil.parser import parse
from django.conf import settings
from django.db import transaction
from django_fsm import can_proceed
from enumfields import Enum
from enumfields.drf.serializers import EnumSupportSerializerMixin
from jose import jws, JWSError
from rest_framework import exceptions, status, serializers as rest_serializers
from rest_framework.fields import SkipField
from rest_framework.utils import model_meta
from rest_framework_json_api import serializers

from apps.shipments.models import Shipment, Device, Location, LoadShipment, FundingType, EscrowState, ShipmentState, \
    TrackingData, PermissionLink, ExceptionType, TransitState
from apps.utils import UpperEnumField


LOG = logging.getLogger('transmission')


class NullableFieldsMixin:
    def to_representation(self, instance):
        # Remove null fields from serialized object
        ret = OrderedDict()
        fields = [field for field in self.fields.values() if not field.write_only]

        for field in fields:
            try:
                attribute = field.get_attribute(instance)
            except SkipField:
                continue

            if attribute is not None:
                representation = field.to_representation(attribute)
                if representation is None:
                    # Do not serialize empty objects
                    continue
                if isinstance(representation, list) and not representation:
                    # Do not serialize empty lists
                    continue
                ret[field.field_name] = representation

        return ret


class DeviceSerializer(NullableFieldsMixin, serializers.ModelSerializer):
    class Meta:
        model = Device
        exclude = ('certificate_id', )


class LocationSerializer(NullableFieldsMixin, serializers.ModelSerializer):
    """
    Serializer for a location, used nested in a Shipment
    """

    class Meta:
        model = Location
        fields = '__all__'


class LocationVaultSerializer(NullableFieldsMixin, serializers.ModelSerializer):
    """
    Serializer for a location, used nested in a Shipment
    """

    class Meta:
        model = Location
        exclude = ('geometry',)


class LoadShipmentSerializer(NullableFieldsMixin, serializers.ModelSerializer):
    """
    Serializer for a location, used nested in a Shipment
    """
    funding_type = UpperEnumField(FundingType, ints_as_names=True)
    escrow_state = UpperEnumField(EscrowState, ints_as_names=True)
    shipment_state = UpperEnumField(ShipmentState, ints_as_names=True)

    class Meta:
        model = LoadShipment
        fields = '__all__'


class ShipmentSerializer(EnumSupportSerializerMixin, serializers.ModelSerializer):
    """
    Serializer for a shipment object
    """
    load_data = LoadShipmentSerializer(source='loadshipment', required=False)
    ship_from_location = LocationSerializer(required=False)
    ship_to_location = LocationSerializer(required=False)
    bill_to_location = LocationSerializer(required=False)
    final_destination_location = LocationSerializer(required=False)
    device = DeviceSerializer(required=False)

    state = UpperEnumField(TransitState, lenient=True, ints_as_names=True, required=False, read_only=True)
    exception = UpperEnumField(ExceptionType, lenient=True, ints_as_names=True, required=False)

    class Meta:
        model = Shipment
        exclude = ('version', 'background_data_hash_interval', 'manual_update_hash_interval')
        read_only_fields = ('owner_id', 'contract_version',) if settings.PROFILES_ENABLED else ('contract_version',)

    class JSONAPIMeta:
        included_resources = ['ship_from_location', 'ship_to_location', 'bill_to_location',
                              'final_destination_location', 'load_data', 'device']


class ShipmentCreateSerializer(ShipmentSerializer):
    device_id = serializers.CharField(max_length=36, required=False)

    def create(self, validated_data):
        extra_args = {}

        with transaction.atomic():
            for location_field in ['ship_from_location', 'ship_to_location', 'bill_to_location']:
                if location_field in validated_data:
                    data = validated_data.pop(location_field)
                    extra_args[location_field] = Location.objects.create(**data)

            if 'device' in self.context:
                extra_args['device'] = self.context['device']

            return Shipment.objects.create(**validated_data, **extra_args)

    def validate_device_id(self, device_id):
        auth = self.context['auth']

        device = Device.get_or_create_with_permission(auth, device_id)
        if hasattr(device, 'shipment'):
            if TransitState(device.shipment.state) == TransitState.IN_TRANSIT:
                raise serializers.ValidationError('Device is already assigned to a Shipment in progress')
            else:
                shipment = Shipment.objects.filter(device_id=device.id).first()
                shipment.device_id = None
                shipment.save()
        self.context['device'] = device

        return device_id

    def validate_shipper_wallet_id(self, shipper_wallet_id):
        if settings.PROFILES_ENABLED:
            response = settings.REQUESTS_SESSION.get(f'{settings.PROFILES_URL}/api/v1/wallet/{shipper_wallet_id}/',
                                                     headers={'Authorization': 'JWT {}'.format(self.context['auth'])})

            if response.status_code != status.HTTP_200_OK:
                raise serializers.ValidationError('User does not have access to this wallet in ShipChain Profiles')

        return shipper_wallet_id

    def validate_storage_credentials_id(self, storage_credentials_id):
        if settings.PROFILES_ENABLED:
            response = settings.REQUESTS_SESSION.get(
                f'{settings.PROFILES_URL}/api/v1/storage_credentials/{storage_credentials_id}/',
                headers={'Authorization': 'JWT {}'.format(self.context['auth'])})

            if response.status_code != status.HTTP_200_OK:
                raise serializers.ValidationError(
                    'User does not have access to this storage credential in ShipChain Profiles')

        return storage_credentials_id


class ShipmentUpdateSerializer(ShipmentSerializer):
    device_id = serializers.CharField(max_length=36, allow_null=True)

    class Meta:
        model = Shipment
        exclude = (('owner_id', 'version', 'background_data_hash_interval', 'manual_update_hash_interval')
                   if settings.PROFILES_ENABLED else ('version', 'background_data_hash_interval',
                                                      'manual_update_hash_interval'))
        read_only_fields = ('vault_id', 'vault_uri', 'shipper_wallet_id', 'carrier_wallet_id',
                            'storage_credentials_id', 'contract_version', 'state')

    def update(self, instance, validated_data):     # noqa: MC0001
        if 'device' in self.context:
            if validated_data['device_id']:
                instance.device = self.context['device']
            else:
                instance.device = validated_data.pop('device_id')

        for location_field in ['ship_from_location', 'ship_to_location',
                               'final_destination_location', 'bill_to_location']:
            if location_field in validated_data:
                location = getattr(instance, location_field)
                data = validated_data.pop(location_field)

                if location:
                    for attr, value in data.items():
                        setattr(location, attr, value)
                    location.save()

                else:
                    location = Location.objects.create(**data)
                    setattr(instance, location_field, location)

        info = model_meta.get_field_info(instance)
        for attr, value in validated_data.items():
            if attr in info.relations and info.relations[attr].to_many:
                field = getattr(instance, attr)
                field.set(value)
            elif attr in ('customer_fields', ):
                previous_value = getattr(instance, attr)
                if previous_value and value:
                    value = {**previous_value, **value}
            setattr(instance, attr, value)

        instance.save()
        return instance

    def validate_device_id(self, device_id):
        auth = self.context['auth']
        if not device_id:
            if not self.instance.device:
                return None
            if TransitState(self.instance.state) == TransitState.IN_TRANSIT:
                raise serializers.ValidationError('Cannot remove device from Shipment in progress')
            return None

        device = Device.get_or_create_with_permission(auth, device_id)

        if hasattr(device, 'shipment'):
            if TransitState(device.shipment.state) == TransitState.IN_TRANSIT:
                raise serializers.ValidationError('Device is already assigned to a Shipment in progress')
            else:
                shipment = Shipment.objects.filter(device_id=device.id).first()
                shipment.device_id = None
                shipment.save()
        self.context['device'] = device

        return device_id

    def validate_delivery_act(self, delivery_act):
        if delivery_act <= datetime.now(timezone.utc):
            return delivery_act
        raise serializers.ValidationError('Cannot update Shipment with future delivery_act')


class PermissionLinkSerializer(serializers.ModelSerializer):
    shipment_id = serializers.CharField(max_length=36, required=False)

    class Meta:
        model = PermissionLink
        fields = '__all__'
        read_only = ('shipment',)

    def validate_expiration_date(self, expiration_date):
        if expiration_date <= datetime.now(timezone.utc):
            raise exceptions.ValidationError('The expiration date should be greater than actual date')
        return expiration_date


class PermissionLinkCreateSerializer(PermissionLinkSerializer):
    emails = serializers.ListField(
        child=serializers.EmailField(),
        min_length=0,
        required=False
    )

    class Meta:
        model = PermissionLink
        fields = ('name', 'expiration_date', 'emails')
        read_only = ('shipment',)


class ShipmentTxSerializer(serializers.ModelSerializer):
    async_job_id = serializers.CharField(max_length=36)

    load_data = LoadShipmentSerializer(source='loadshipment', required=False)
    ship_from_location = LocationSerializer(required=False)
    ship_to_location = LocationSerializer(required=False)
    bill_to_location = LocationSerializer(required=False)
    final_destination_location = LocationSerializer(required=False)
    device = DeviceSerializer(required=False)

    state = UpperEnumField(TransitState, ints_as_names=True)
    exception = UpperEnumField(ExceptionType, ints_as_names=True)

    class Meta:
        model = Shipment
        exclude = ('version', 'background_data_hash_interval', 'manual_update_hash_interval')
        meta_fields = ('async_job_id',)
        if settings.PROFILES_ENABLED:
            read_only_fields = ('owner_id',)

    class JSONAPIMeta:
        included_resources = ['ship_from_location', 'ship_to_location', 'bill_to_location',
                              'final_destination_location', 'load_data', 'device']


class ShipmentVaultSerializer(NullableFieldsMixin, serializers.ModelSerializer):
    """
    Serializer for a shipment vault object
    """

    ship_from_location = LocationVaultSerializer(required=False)
    ship_to_location = LocationVaultSerializer(required=False)
    bill_to_location = LocationVaultSerializer(required=False)
    final_destination_location = LocationSerializer(required=False)

    class Meta:
        model = Shipment
        exclude = ('owner_id', 'storage_credentials_id',
                   'vault_id', 'vault_uri', 'shipper_wallet_id', 'carrier_wallet_id',
                   'contract_version', 'device', 'updated_by', 'state', 'exception', 'delayed', 'expected_delay_hours')


class TrackingDataSerializer(serializers.Serializer):
    payload = serializers.RegexField(r'^[a-zA-Z0-9\-_]+?\.[a-zA-Z0-9\-_]+?\.([a-zA-Z0-9\-_]+)?$')

    def validate(self, attrs):  # noqa: MC0001
        iot = boto3.client('iot', region_name='us-east-1')
        payload = attrs['payload']
        shipment = self.context['shipment']
        try:
            header = jws.get_unverified_header(payload)
        except JWSError as exc:
            raise exceptions.ValidationError(f"Invalid JWS: {exc}")

        certificate_id_from_payload = header['kid']

        # Ensure that the device is allowed to update the Shipment tracking data
        if not shipment.device:
            raise exceptions.PermissionDenied(f"No device for shipment {shipment.id}")

        elif certificate_id_from_payload != shipment.device.certificate_id:
            try:
                iot.describe_certificate(certificateId=certificate_id_from_payload)
            except BotoCoreError as exc:
                LOG.warning(f'Found dubious certificate: {certificate_id_from_payload}, on shipment: {shipment.id}')
                raise exceptions.PermissionDenied(f"Certificate: {certificate_id_from_payload}, is invalid: {exc}")

            device = shipment.device
            device.certificate_id = Device.get_valid_certificate(device.id)
            device.save()

            if certificate_id_from_payload != device.certificate_id:
                raise exceptions.PermissionDenied(f"Certificate {certificate_id_from_payload} is "
                                                  f"not associated with shipment {shipment.id}")

        try:
            # Look up JWK for device from AWS IoT
            cert = iot.describe_certificate(certificateId=certificate_id_from_payload)

            if cert['certificateDescription']['status'] == 'ACTIVE':
                # Get public key PEM from x509 cert
                certificate = cert['certificateDescription']['certificatePem'].encode()
                public_key = x509.load_pem_x509_certificate(certificate, default_backend()).public_key().public_bytes(
                    encoding=Encoding.PEM, format=PublicFormat.SubjectPublicKeyInfo).decode()

                # Validate authenticity and integrity of message signature
                attrs['payload'] = json.loads(jws.verify(payload, public_key, header['alg']).decode("utf-8"))
            else:
                raise exceptions.PermissionDenied(f"Certificate {certificate_id_from_payload} is "
                                                  f"not ACTIVE in IoT for shipment {shipment.id}")
        except ClientError as exc:
            raise exceptions.APIException(f'boto3 error when validating tracking update: {exc}')
        except JWSError as exc:
            raise exceptions.PermissionDenied(f'Error validating tracking data JWS: {exc}')

        return attrs


class UnvalidatedTrackingDataSerializer(serializers.Serializer):
    payload = serializers.JSONField()

    def validate(self, attrs):
        shipment = self.context['shipment']

        # Ensure that the device is allowed to update the Shipment tracking data
        if not shipment.device:
            raise exceptions.PermissionDenied(f"No device for shipment {shipment.id}")

        return attrs


class TrackingDataToDbSerializer(rest_serializers.ModelSerializer):
    """
    Serializer for tracking data to be cached in db
    """
    shipment = ShipmentSerializer(read_only=True)

    def __init__(self, *args, **kwargs):
        # Flatten 'position' fields to the parent tracking data payload
        kwargs['data'].update(kwargs['data'].pop('position'))

        # Ensure that the timestamps is valid
        try:
            kwargs['data']['timestamp'] = parse(kwargs['data']['timestamp'])
        except Exception as exception:
            raise exceptions.ValidationError(detail=f"Unable to parse tracking data timestamp in to datetime object: \
                                                    {exception}")

        super().__init__(*args, **kwargs)

    class Meta:
        model = TrackingData
        exclude = ('point', 'time', 'device')

    def create(self, validated_data):
        return TrackingData.objects.create(**validated_data, **self.context)


class ChangesDiffSerializer:
    relation_fields = settings.RELATED_FIELDS_WITH_HISTORY_MAP.keys()
    excluded_fields = ('history_user', 'version', 'customer_fields', 'geometry',
                       'background_data_hash_interval', 'manual_update_hash_interval')

    # Enum field serializers
    stateEnumSerializer = UpperEnumField(TransitState, lenient=True, ints_as_names=True, read_only=True)
    exceptionEnumSerializer = UpperEnumField(ExceptionType, lenient=True, ints_as_names=True, read_only=True)

    def __init__(self, queryset, request):
        self.queryset = queryset
        self.request = request

    def diff_object_fields(self, old, new):
        changes = new.diff(old)

        flat_changes = self.build_list_changes(changes)
        relation_changes = self.relation_changes(new)
        flat_changes.extend(self.json_field_changes(new, old))

        return {
            'history_date': new.history_date,
            'fields': flat_changes,
            'relationships': relation_changes if relation_changes else None,
            'author': new.history_user,
        }

    def get_enum_representation(self, field_name, field_value):
        representation = field_value
        # The initial enum values are None
        if field_value is not None:
            # We wrap this in a try:except to avoid fields like Location.state
            try:
                representation = getattr(self, f'{field_name}EnumSerializer').to_representation(field_value)
            except (AttributeError, ValueError):
                pass
        return representation

    def build_list_changes(self, changes, json_field=False, base_field=None):
        field_list = []
        if changes is None:
            return field_list

        changes_list = [change for change in changes.changes if change.field not in self.excluded_fields]
        for change in changes_list:
            field = {
                'field': change.field if not json_field else f'{base_field}.{change.field}',
                'old': self.get_enum_representation(change.field, change.old),
                'new': self.get_enum_representation(change.field, change.new)
            }

            if change.field in self.relation_fields:
                if change.old is None:
                    # The relationship field is created
                    field['new'] = Location.history.filter(pk=change.new).first().instance.id
                if change.old and change.new:
                    # The relationship field has been modified no need to include it in flat changes
                    continue

            field_list.append(field)
        return field_list

    def relation_changes(self, new_historical):
        relations_map = {}
        for relation in self.relation_fields:
            historical_relation = getattr(new_historical, relation, None)
            changes = None
            if historical_relation:
                date_max = new_historical.history_date
                date_min = date_max - timedelta(milliseconds=settings.SIMPLE_HISTORY_RELATED_WINDOW_MS)
                if new_historical.history_user == historical_relation.history_user and \
                        date_min <= historical_relation.history_date <= date_max:
                    # The relationship field has changed
                    changes = historical_relation.diff(historical_relation.prev_record)
            if changes:
                relations_map[relation] = self.build_list_changes(changes)

        return relations_map

    def json_field_changes(self, new_obj, old_obj):
        changes_list = []
        # JsonFields changes between the two historical objects
        json_fields_changes = new_obj.diff(old_obj, json_fields_only=True)
        if json_fields_changes:
            for field_name, changes in json_fields_changes.items():
                related_changes = self.build_list_changes(changes, json_field=True, base_field=field_name)
                if related_changes:
                    changes_list.extend(related_changes)
        return changes_list

    @property
    def data(self):
        queryset = self.queryset
        count = queryset.count()

        queryset_diff = []
        if count == 0:
            return queryset_diff
        index = 0
        if count > 1:
            while index + 1 < count:
                new = queryset[index]
                old = queryset[index + 1]
                index += 1
                queryset_diff.append(self.diff_object_fields(old, new))

        if not self.request.query_params.get('history_date__gte'):
            queryset_diff.append(self.diff_object_fields(None, queryset[index]))

        return queryset_diff


class DevicesQueryParamsSerializer(serializers.Serializer):
    active = serializers.BooleanField(required=False, allow_null=True, default=None)
    in_bbox = serializers.CharField(required=False, allow_null=True, default=None)

    def validate_in_bbox(self, in_bbox):
        long_range = (-180, 180)
        lat_range = (-90, 90)
        box_ranges = (long_range, lat_range, long_range, lat_range)

        if in_bbox:
            box_to_list = in_bbox.split(',')
            if not len(box_to_list) == 4:
                raise exceptions.ValidationError(f'in_box parameter takes 4 position parameters but '
                                                 f'{len(box_to_list)}, were passed in.')

            in_bbox_num = []
            for box_value, rang, index in zip(box_to_list, box_ranges, range(1, 5)):
                try:
                    box_value = float(box_value)
                    in_bbox_num.append(box_value)
                except ValueError:
                    raise exceptions.ValidationError(f'in_bbox coordinate: {box_value}, should be type number')

                if not rang[0] <= box_value <= rang[1]:
                    raise exceptions.ValidationError(f'in_bbox coordinate in position: '
                                                     f'{index}, value: {box_value}, should be in range: {rang}')

            if in_bbox_num[2] <= in_bbox_num[0] or in_bbox_num[3] <= in_bbox_num[1]:
                raise exceptions.ValidationError('Invalid geo box, make sure that: '
                                                 'in_bbox[1] < in_bbox[3] and in_bbox[2] < in_bbox[4].')

            return ','.join([c.strip() for c in in_bbox.split(',')])

        return None


class ActionType(Enum):
    PICK_UP = partial(Shipment.pick_up)
    ARRIVAL = partial(Shipment.arrival)
    DROP_OFF = partial(Shipment.drop_off)


class ShipmentActionRequestSerializer(serializers.Serializer):
    action_type = UpperEnumField(ActionType, lenient=True, ints_as_names=True)
    tracking_data = serializers.CharField(required=False, allow_null=True)
    document_id = serializers.CharField(required=False, allow_null=True)

    def validate_action_type(self, action_type):
        shipment = self.context['shipment']
        action_type.value.func.__self__ = shipment  # Hack for getting dynamic partial funcs to work w/ can_proceed
        if not can_proceed(action_type.value.func):
            # Bad state transition
            raise exceptions.ValidationError(f'Action {action_type.name} not available while Shipment '
                                             f'is in state {TransitState(shipment.state).name}')
        return action_type
