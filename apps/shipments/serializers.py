import json
from collections import OrderedDict
from datetime import datetime, timezone

import boto3
from botocore.exceptions import ClientError
from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from dateutil.parser import parse
from django.conf import settings
from django.db import transaction
from enumfields.drf.serializers import EnumSupportSerializerMixin
from jose import jws, JWSError
from rest_framework import exceptions, status, serializers as rest_serializers
from rest_framework.fields import SkipField
from rest_framework.utils import model_meta
from rest_framework_json_api import serializers

from apps.shipments.models import Shipment, Device, Location, LoadShipment, FundingType, EscrowState, ShipmentState, \
    TrackingData, PermissionLink
from apps.utils import UpperEnumField


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
        fields = '__all__'


class LocationSerializer(NullableFieldsMixin, serializers.ModelSerializer):
    """
    Serializer for a location, used nested in a Shipment
    """

    class Meta:
        model = Location
        exclude = ('owner_id',) if settings.PROFILES_ENABLED else ()


class LocationVaultSerializer(NullableFieldsMixin, serializers.ModelSerializer):
    """
    Serializer for a location, used nested in a Shipment
    """

    class Meta:
        model = Location
        exclude = ('owner_id', 'geometry')


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


class ShipmentSerializer(serializers.ModelSerializer, EnumSupportSerializerMixin):
    """
    Serializer for a shipment object
    """
    load_data = LoadShipmentSerializer(source='loadshipment', required=False)
    ship_from_location = LocationSerializer(required=False)
    ship_to_location = LocationSerializer(required=False)
    bill_to_location = LocationSerializer(required=False)
    device = DeviceSerializer(required=False)

    class Meta:
        model = Shipment
        exclude = ('owner_id', 'version') if settings.PROFILES_ENABLED else ('version',)
        read_only_fields = ('contract_version',)

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
                    if 'owner_id' not in data:
                        data['owner_id'] = validated_data['owner_id']
                    extra_args[location_field], _ = Location.objects.get_or_create(**data)

            if 'device' in self.context:
                extra_args['device'] = self.context['device']

            return Shipment.objects.create(**validated_data, **extra_args)

    def validate_device_id(self, device_id):
        auth = self.context['auth']

        device = Device.get_or_create_with_permission(auth, device_id)
        if hasattr(device, 'shipment'):
            if not device.shipment.delivery_act:
                raise serializers.ValidationError('Device is already assigned to a Shipment in progress')
            else:
                Shipment.objects.filter(device_id=device.id).update(device=None)
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
        exclude = ('owner_id', 'version') if settings.PROFILES_ENABLED else ('version',)
        read_only_fields = ('vault_id', 'vault_uri', 'shipper_wallet_id', 'carrier_wallet_id',
                            'storage_credentials_id', 'contract_version')

    def update(self, instance, validated_data):
        if 'device' in self.context:
            if validated_data['device_id']:
                instance.device = self.context['device']
            else:
                instance.device = validated_data.pop('device_id')

        for location_field in ['ship_from_location', 'ship_to_location', 'bill_to_location']:
            if location_field in validated_data:
                location = getattr(instance, location_field)
                data = validated_data.pop(location_field)

                if location:
                    for attr, value in data.items():
                        setattr(location, attr, value)
                    location.save()

                else:
                    location, _ = Location.objects.get_or_create(**data)
                    setattr(instance, location_field, location)

        info = model_meta.get_field_info(instance)
        for attr, value in validated_data.items():
            if attr in info.relations and info.relations[attr].to_many:
                field = getattr(instance, attr)
                field.set(value)
            else:
                setattr(instance, attr, value)

        instance.save()
        return instance

    def validate_device_id(self, device_id):
        auth = self.context['auth']
        if not device_id:
            print('In validate_device_id: ', device_id)
            if not self.instance.device:
                return None
            if not self.instance.delivery_act or self.instance.delivery_act >= datetime.now(timezone.utc):
                raise serializers.ValidationError('Cannot remove device from Shipment in progress')
            return None

        device = Device.get_or_create_with_permission(auth, device_id)

        if hasattr(device, 'shipment'):
            if not device.shipment.delivery_act:
                raise serializers.ValidationError('Device is already assigned to a Shipment in progress')
            else:
                Shipment.objects.filter(device_id=device.id).update(device=None)
        self.context['device'] = device

        return device_id


class PermissionLinkSerializer(serializers.ModelSerializer):
    shipment_id = serializers.CharField(max_length=36, required=False)

    class Meta:
        model = PermissionLink
        exclude = ('shipment', )

    def validate(self, attrs):
        attrs['shipment_id'] = self.context['shipment_id']
        return attrs


class ShipmentTxSerializer(serializers.ModelSerializer):
    async_job_id = serializers.CharField(max_length=36)

    load_data = LoadShipmentSerializer(source='loadshipment', required=False)
    ship_from_location = LocationSerializer(required=False)
    ship_to_location = LocationSerializer(required=False)
    bill_to_location = LocationSerializer(required=False)
    device = DeviceSerializer(required=False)

    class Meta:
        model = Shipment
        exclude = ('owner_id', 'version') if settings.PROFILES_ENABLED else ('version',)
        meta_fields = ('async_job_id',)

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

    class Meta:
        model = Shipment
        exclude = ('owner_id', 'storage_credentials_id',
                   'vault_id', 'vault_uri', 'shipper_wallet_id', 'carrier_wallet_id',
                   'contract_version', 'device', 'updated_by')


class TrackingDataSerializer(serializers.Serializer):
    payload = serializers.RegexField(r'^[a-zA-Z0-9\-_]+?\.[a-zA-Z0-9\-_]+?\.([a-zA-Z0-9\-_]+)?$')

    def validate(self, attrs):
        payload = attrs['payload']
        shipment = self.context['shipment']
        try:
            header = jws.get_unverified_header(payload)
        except JWSError as exc:
            raise exceptions.ValidationError(f"Invalid JWS: {exc}")

        # Ensure that the device is allowed to update the Shipment tracking data
        if not shipment.device:
            raise exceptions.PermissionDenied(f"No device for shipment {shipment.id}")
        elif header['kid'] != shipment.device.certificate_id:
            raise exceptions.PermissionDenied(f"Certificate {header['kid']} is "
                                              f"not associated with shipment {shipment.id}")

        try:
            # Look up JWK for device from AWS IoT
            iot = boto3.client('iot', region_name='us-east-1')
            cert = iot.describe_certificate(certificateId=header['kid'])

            if cert['certificateDescription']['status'] == 'ACTIVE':
                # Get public key PEM from x509 cert
                certificate = cert['certificateDescription']['certificatePem'].encode()
                public_key = x509.load_pem_x509_certificate(certificate, default_backend()).public_key().public_bytes(
                    encoding=Encoding.PEM, format=PublicFormat.SubjectPublicKeyInfo).decode()

                # Validate authenticity and integrity of message signature
                attrs['payload'] = json.loads(jws.verify(payload, public_key, header['alg']).decode("utf-8"))
            else:
                raise exceptions.PermissionDenied(f"Certificate {header['kid']} is "
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
