"""
Copyright 2020 ShipChain, Inc.

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
from rest_framework import serializers
from shipchain_common.authentication import get_jwt_from_request

from apps.routes.models import Route
from apps.routes.serializers.route_leg import RouteLegInfoSerializer
from apps.shipments.models import Device
from apps.shipments.serializers import DeviceSerializer


class RouteSerializer(serializers.ModelSerializer):
    legs = RouteLegInfoSerializer(source='routeleg_set', required=False, many=True)
    device = DeviceSerializer(required=False)

    included_serializers = {
        'legs': RouteLegInfoSerializer,
        'device': DeviceSerializer,
    }

    class Meta:
        model = Route
        fields = ('name', 'driver_id', 'device', 'legs', 'owner_id')
        read_only_fields = ['legs', 'owner_id']

    class JSONAPIMeta:
        included_resources = ['legs', 'device']

    @property
    def auth(self):
        return get_jwt_from_request(self.context['request'])


class RouteCreateSerializer(RouteSerializer):
    device_id = serializers.UUIDField(required=False, allow_null=True)

    class Meta:
        model = Route
        fields = ('name', 'driver_id', 'device_id')

    def validate_device_id(self, device_id):
        device = Device.get_or_create_with_permission(self.auth, device_id)
        device.prepare_for_reassignment()

        return device_id


class RouteUpdateSerializer(RouteSerializer):
    device_id = serializers.UUIDField(required=False, allow_null=True)

    class Meta:
        model = Route
        fields = ('name', 'driver_id', 'device_id')

    def update(self, instance, validated_data):
        if 'device_id' in validated_data:
            instance.device_id = validated_data.pop('device_id')

        return super().update(instance, validated_data)

    def validate_device_id(self, device_id):
        if not device_id:
            if not self.instance.device:
                return None
            if not self.instance.can_disassociate_device():
                raise serializers.ValidationError('Cannot remove device from Route in progress')
            return None

        device = Device.get_or_create_with_permission(self.auth, device_id)
        device.prepare_for_reassignment()

        return device_id


class RouteOrderSerializer(serializers.ModelSerializer):
    """
    Serializer for RouteLeg reordering.
    """
    legs = serializers.ListSerializer(child=serializers.UUIDField())

    class Meta:
        model = Route
        fields = ('legs',)

    def create(self, validated_data):
        raise NotImplementedError

    def update(self, instance, validated_data):
        raise NotImplementedError

    def validate_legs(self, legs):
        if sorted(map(str, legs)) != sorted(map(lambda leg: str(leg['pk']),
                                                self.instance.routeleg_set.all().values('pk'))):
            raise serializers.ValidationError('Reorder list does not contain exact list of existing RouteLegs')

        return legs
