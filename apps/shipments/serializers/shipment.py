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

import json
from collections import OrderedDict
from datetime import datetime, timezone

from django.conf import settings
from django.db import transaction
from enumfields.drf.serializers import EnumSupportSerializerMixin
from rest_framework import status
from rest_framework.exceptions import PermissionDenied
from rest_framework.fields import SkipField
from rest_framework.utils import model_meta
from rest_framework_json_api import serializers
from shipchain_common.authentication import get_jwt_from_request
from shipchain_common.utils import UpperEnumField, validate_uuid4

from ..models import Shipment, Device, Location, LoadShipment, FundingType, EscrowState, ShipmentState, \
    ExceptionType, TransitState, ShipmentTag
from .tags import ShipmentTagSerializer


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


class GeofenceListField(serializers.ListField):
    def to_internal_value(self, data):
        # In order to support form-data requests, we have to parse json-formatted geofence data
        # ListFields come back like geofences: ["["geofence-id", "geofence2-id"]"]
        if len(data) == 1:
            try:
                data = json.loads(data[0])
            except (json.JSONDecodeError, TypeError):
                pass
        return super().to_internal_value(data)


class FKShipmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Shipment
        fields = ('id',)


class ShipmentSerializer(EnumSupportSerializerMixin, serializers.ModelSerializer):
    """
    Serializer for a shipment object
    """
    load_data = LoadShipmentSerializer(source='loadshipment', required=False)

    geofences = GeofenceListField(child=serializers.CharField(), required=False)

    state = UpperEnumField(TransitState, lenient=True, ints_as_names=True, required=False, read_only=True)
    exception = UpperEnumField(ExceptionType, lenient=True, ints_as_names=True, required=False)
    tags = serializers.ResourceRelatedField(many=True, required=False, read_only=True, source='shipment_tags')

    included_serializers = {
        'ship_from_location': LocationSerializer,
        'ship_to_location': LocationSerializer,
        'bill_to_location': LocationSerializer,
        'final_destination_location': LocationSerializer,
        'load_data': LoadShipmentSerializer,
        'device': DeviceSerializer,
        'tags': ShipmentTagSerializer,
    }

    class Meta:
        model = Shipment
        exclude = ('version', 'background_data_hash_interval', 'manual_update_hash_interval', 'asset_physical_id')
        read_only_fields = ('owner_id', 'contract_version',) if settings.PROFILES_ENABLED else ('contract_version',)

    class JSONAPIMeta:
        included_resources = ['ship_from_location', 'ship_to_location', 'bill_to_location',
                              'final_destination_location', 'load_data', 'tags', ]

    @property
    def user(self):
        return self.context['request'].user

    @property
    def auth(self):
        return get_jwt_from_request(self.context['request'])

    def validate_geofences(self, geofences):
        for geofence in geofences:
            if not validate_uuid4(geofence):
                raise serializers.ValidationError(f'Invalid UUIDv4 {geofence} provided in Geofences')

        # Deduplicate list
        return list(set(geofences))


class ShipmentCreateSerializer(ShipmentSerializer):
    device_id = serializers.CharField(max_length=36, required=False)
    ship_from_location = LocationSerializer(required=False)
    ship_to_location = LocationSerializer(required=False)
    bill_to_location = LocationSerializer(required=False)
    final_destination_location = LocationSerializer(required=False)
    device = DeviceSerializer(required=False)
    tags = serializers.ListField(
        child=serializers.DictField(child=serializers.CharField(max_length=50)),
        required=False
    )

    def create(self, validated_data):
        extra_args = {}

        with transaction.atomic():
            for location_field in ['ship_from_location', 'ship_to_location', 'bill_to_location']:
                if location_field in validated_data:
                    data = validated_data.pop(location_field)
                    extra_args[location_field] = Location.objects.create(**data)

            if 'device' in self.context:
                extra_args['device'] = self.context['device']

            if 'tags' in validated_data:
                shipment_tags = validated_data.pop('tags')
                shipment = Shipment.objects.create(**validated_data, **extra_args)
                for shipment_tag in shipment_tags:
                    ShipmentTag.objects.create(
                        tag_type=shipment_tag['tag_type'],
                        tag_value=shipment_tag['tag_value'],
                        shipment_id=shipment.id,
                        owner_id=shipment.owner_id
                    )
            else:
                shipment = Shipment.objects.create(**validated_data, **extra_args)

            return shipment

    def validate_tags(self, tags):
        if len(tags) != len([set(t) for t in {tuple(d.items()) for d in tags}]):
            raise serializers.ValidationError('Tags field cannot contain duplicates')

        for tag_dict in tags:
            if 'tag_value' not in tag_dict or 'tag_type' not in tag_dict:
                raise serializers.ValidationError('Tags items must contain `tag_value` and `tag_type`.')

        return tags

    def validate_device_id(self, device_id):
        device = Device.get_or_create_with_permission(self.auth, device_id)
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
                                                     headers={'Authorization': 'JWT {}'.format(self.auth)})

            if response.status_code != status.HTTP_200_OK:
                raise serializers.ValidationError('User does not have access to this wallet in ShipChain Profiles')

        return shipper_wallet_id

    def validate_storage_credentials_id(self, storage_credentials_id):
        if settings.PROFILES_ENABLED:
            response = settings.REQUESTS_SESSION.get(
                f'{settings.PROFILES_URL}/api/v1/storage_credentials/{storage_credentials_id}/',
                headers={'Authorization': 'JWT {}'.format(self.auth)})

            if response.status_code != status.HTTP_200_OK:
                raise serializers.ValidationError(
                    'User does not have access to this storage credential in ShipChain Profiles')

        return storage_credentials_id

    def validate_gtx_required(self, gtx_required):
        if settings.PROFILES_ENABLED:
            if gtx_required and not self.user.has_perm('gtx.shipment_use'):
                raise PermissionDenied('User does not have access to enable GTX for this shipment')
        return gtx_required


class ShipmentUpdateSerializer(ShipmentSerializer):
    device_id = serializers.CharField(max_length=36, allow_null=True)
    ship_from_location = LocationSerializer(required=False)
    ship_to_location = LocationSerializer(required=False)
    bill_to_location = LocationSerializer(required=False)
    final_destination_location = LocationSerializer(required=False)
    device = DeviceSerializer(required=False)

    class Meta:
        model = Shipment
        exclude = (('owner_id', 'version',
                    'background_data_hash_interval', 'manual_update_hash_interval', 'asset_physical_id')
                   if settings.PROFILES_ENABLED else ('version', 'background_data_hash_interval',
                                                      'manual_update_hash_interval', 'asset_physical_id'))
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
        if not device_id:
            if not self.instance.device:
                return None
            if TransitState(self.instance.state) == TransitState.IN_TRANSIT:
                raise serializers.ValidationError('Cannot remove device from Shipment in progress')
            return None

        device = Device.get_or_create_with_permission(self.auth, device_id)

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

    def validate_gtx_required(self, gtx_required):
        if self.instance.gtx_required == gtx_required:
            return gtx_required

        if settings.PROFILES_ENABLED:
            if (self.instance.gtx_required or gtx_required) and not self.user.has_perm('gtx.shipment_use'):
                raise PermissionDenied('User does not have access to modify GTX for this shipment')

        if TransitState(self.instance.state).value > TransitState.AWAITING_PICKUP.value:
            raise serializers.ValidationError('Cannot modify GTX for a shipment in progress')

        return gtx_required


class ShipmentTxSerializer(serializers.ModelSerializer):
    async_job_id = serializers.CharField(max_length=36)

    load_data = LoadShipmentSerializer(source='loadshipment', required=False)

    state = UpperEnumField(TransitState, ints_as_names=True)
    exception = UpperEnumField(ExceptionType, ints_as_names=True)

    tags = serializers.ResourceRelatedField(many=True, required=False, read_only=True, source='shipment_tags')

    included_serializers = {
        'ship_from_location': LocationSerializer,
        'ship_to_location': LocationSerializer,
        'bill_to_location': LocationSerializer,
        'final_destination_location': LocationSerializer,
        'load_data': LoadShipmentSerializer,
        'device': DeviceSerializer,
        'tags': ShipmentTagSerializer,
    }

    class Meta:
        model = Shipment
        exclude = ('version', 'background_data_hash_interval', 'manual_update_hash_interval', 'asset_physical_id')
        meta_fields = ('async_job_id',)
        if settings.PROFILES_ENABLED:
            read_only_fields = ('owner_id',)

    class JSONAPIMeta:
        included_resources = ['ship_from_location', 'ship_to_location', 'bill_to_location',
                              'final_destination_location', 'load_data', 'tags']


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
        exclude = ('owner_id', 'storage_credentials_id', 'background_data_hash_interval',
                   'vault_id', 'vault_uri', 'shipper_wallet_id', 'carrier_wallet_id', 'manual_update_hash_interval',
                   'contract_version', 'device', 'updated_by', 'state', 'exception', 'delayed', 'expected_delay_hours',
                   'geofences', 'assignee_id', 'gtx_required')


class ShipmentOverviewSerializer(serializers.ModelSerializer):
    state = UpperEnumField(TransitState, ints_as_names=True)
    exception = UpperEnumField(ExceptionType, ints_as_names=True)

    class Meta:
        model = Shipment
        fields = ('state', 'exception', 'delayed', )
