from collections import OrderedDict

import boto3
from botocore.exceptions import ClientError
from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from django.conf import settings
from django.db import transaction
from enumfields.drf import EnumField
from enumfields.drf.serializers import EnumSupportSerializerMixin
from jose import jws, JWSError
from rest_framework.fields import SkipField
from rest_framework_json_api import serializers

from apps.shipments.models import Shipment, Device, Location, LoadShipment, FundingType, EscrowStatus, ShipmentStatus


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


class LocationSerializer(NullableFieldsMixin, serializers.ModelSerializer):
    """
    Serializer for a location, used nested in a Shipment
    """

    class Meta:
        model = Location
        fields = '__all__'
        read_only_fields = ('owner_id',) if settings.PROFILES_URL else ()


class LocationVaultSerializer(NullableFieldsMixin, serializers.ModelSerializer):
    """
    Serializer for a location, used nested in a Shipment
    """

    class Meta:
        model = Location
        exclude = ('owner_id',) if settings.PROFILES_URL else ()


class LoadShipmentSerializer(NullableFieldsMixin, serializers.ModelSerializer):
    """
    Serializer for a location, used nested in a Shipment
    """
    funding_type = EnumField(FundingType, ints_as_names=True)
    escrow_status = EnumField(EscrowStatus, ints_as_names=True)
    shipment_status = EnumField(ShipmentStatus, ints_as_names=True)

    class Meta:
        model = LoadShipment
        fields = '__all__'


class ShipmentSerializer(serializers.ModelSerializer, EnumSupportSerializerMixin):
    """
    Serializer for a shipment object
    """
    load_data = LoadShipmentSerializer(required=False)
    ship_from_location = LocationSerializer(required=False)
    ship_to_location = LocationSerializer(required=False)

    transactions = serializers.SerializerMethodField()

    def get_transactions(self, obj):
        return [eth_action.transaction_hash for eth_action in obj.ethaction_set.all()]

    class Meta:
        model = Shipment
        fields = '__all__'
        read_only_fields = ('owner_id', 'contract_version') if settings.PROFILES_URL else ('contract_version',)

    class JSONAPIMeta:
        included_resources = ['ship_from_location', 'ship_to_location',
                              'final_destination_location', 'load_data', 'device']


class ShipmentCreateSerializer(ShipmentSerializer):
    def create(self, validated_data):
        extra_args = {}

        request = self.context['request']

        with transaction.atomic():
            for location_field in ['ship_from_location', 'ship_to_location']:
                if location_field in validated_data:
                    data = validated_data.pop(location_field)

                    extra_args[location_field], _ = Location.objects.get_or_create(**data, owner_id=validated_data[
                        'owner_id'])

            if 'device_id' in validated_data:
                extra_args['device'] = Device.create_with_permission(request.auth, validated_data['device_id'])

            return Shipment.objects.create(**validated_data, **extra_args)


class ShipmentUpdateSerializer(ShipmentSerializer):
    class Meta:
        model = Shipment
        fields = '__all__'
        if settings.PROFILES_URL:
            read_only_fields = ('owner_id', 'vault_id', 'shipper_wallet_id', 'carrier_wallet_id',
                                'storage_credentials_id')
        else:
            read_only_fields = ('vault_id', 'shipper_wallet_id', 'carrier_wallet_id', 'storage_credentials_id')


class ShipmentTxSerializer(serializers.ModelSerializer):
    async_job_id = serializers.CharField(max_length=36)

    load_data = LoadShipmentSerializer(required=False)
    ship_from_location = LocationSerializer(required=False)
    ship_to_location = LocationSerializer(required=False)

    class Meta:
        model = Shipment
        fields = '__all__'
        read_only_fields = ('owner_id',)
        meta_fields = ('async_job_id',)

    class JSONAPIMeta:
        included_resources = ['ship_from_location', 'ship_to_location',
                              'final_destination_location', 'load_data', 'device']


class ShipmentVaultSerializer(NullableFieldsMixin, serializers.ModelSerializer):
    """
    Serializer for a shipment vault object
    """

    ship_from_location = LocationVaultSerializer(required=False)
    ship_to_location = LocationVaultSerializer(required=False)

    class Meta:
        model = Shipment
        exclude = ('owner_id', 'load_data', 'storage_credentials_id',
                   'vault_id', 'shipper_wallet_id', 'carrier_wallet_id',
                   'contract_version')


class TrackingDataSerializer(serializers.Serializer):
    payload = serializers.RegexField(r'^[a-zA-Z0-9\-_]+?\.[a-zA-Z0-9\-_]+?\.([a-zA-Z0-9\-_]+)?$')

    def validate(self, attrs):
        payload = attrs['payload']
        shipment = self.context['shipment']
        try:
            header = jws.get_unverified_header(payload)

            # Ensure that the device is allowed to update the Shipment tracking data
            if header['kid'] != shipment.device.certificate_id:
                raise serializers.ValidationError(f"Certificate {header['kid']} is "
                                                  f"not associated with shipment {shipment.id}")

            # Look up JWK for device from AWS IoT
            iot = boto3.client('iot', region_name='us-east-1')
            cert = iot.describe_certificate(certificateId=header['kid'])

            if cert['certificateDescription']['status'] == 'ACTIVE':
                # Get public key PEM from x509 cert
                certificate = cert['certificateDescription']['certificatePem'].encode()
                public_key = x509.load_pem_x509_certificate(certificate, default_backend()).public_key().public_bytes(
                    encoding=Encoding.PEM, format=PublicFormat.SubjectPublicKeyInfo).decode()

                # Validate authenticity and integrity of message signature
                attrs['payload'] = jws.verify(payload, public_key, header['alg'])
            else:
                raise serializers.ValidationError(f"Certificate {header['kid']} is "
                                                  f"not ACTIVE in IoT for shipment {shipment.id}")
        except ClientError as exc:
            raise serializers.ValidationError(f'boto3 error when validating tracking update: {exc}')
        except JWSError as exc:
            raise serializers.ValidationError(f'Error validating tracking data JWS: {exc}')

        return attrs
