from collections import OrderedDict

from django.conf import settings
from rest_framework.fields import SkipField
from enumfields.drf import EnumField
from enumfields.drf.serializers import EnumSupportSerializerMixin
from rest_framework_json_api import serializers
from apps.shipments.models import Shipment, Location, LoadShipment, FundingType, EscrowStatus, ShipmentStatus


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
        included_resources = ['ship_from_location', 'ship_to_location', 'final_destination_location', 'load_data']


class ShipmentCreateSerializer(ShipmentSerializer):
    def create(self, validated_data):
        location_args = {}

        for location_field in ['ship_from_location', 'ship_to_location']:
            if location_field in validated_data:
                data = validated_data.pop(location_field)

                location_args[location_field], _ = Location.objects.get_or_create(**data)

        return Shipment.objects.create(**validated_data, **location_args)


class ShipmentUpdateSerializer(ShipmentSerializer):
    class Meta:
        model = Shipment
        fields = '__all__'
        if settings.PROFILES_URL:
            read_only_fields = ('owner_id', 'vault_id', 'shipper_wallet_id',
                                'carrier_wallet_id', 'storage_credentials_id')
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
        included_resources = ['ship_from_location', 'ship_to_location', 'final_destination_location', 'load_data']


class ShipmentVaultSerializer(NullableFieldsMixin, serializers.ModelSerializer):
    """
    Serializer for a shipment vault object
    """

    ship_from_location = LocationSerializer(required=False)
    ship_to_location = LocationSerializer(required=False)

    class Meta:
        model = Shipment
        exclude = ('owner_id', 'load_data', 'storage_credentials_id',
                   'vault_id', 'shipper_wallet_id', 'carrier_wallet_id',
                   'contract_version')
