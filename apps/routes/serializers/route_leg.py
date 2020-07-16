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
from django.db import IntegrityError
from rest_framework import serializers
from rest_framework.exceptions import ValidationError

from apps.routes.models import RouteLeg, Route
from apps.shipments.models import Shipment, TransitState
from apps.shipments.permissions import IsOwnerOrShared


class RouteLegInfoSerializer(serializers.ModelSerializer):

    class Meta:
        model = RouteLeg
        fields = ('shipment_id', 'sequence')


class RouteLegCreateSerializer(serializers.ModelSerializer):
    shipment_id = serializers.UUIDField()

    class Meta:
        model = RouteLeg
        fields = ('shipment_id',)

    def validate_shipment_id(self, data):
        shipment = Shipment.objects.filter(pk=data).first()

        if not shipment:
            raise ValidationError(f'Shipment does not exist')

        if not IsOwnerOrShared().has_object_permission(self.context['request'], self.context['view'], shipment):
            raise ValidationError(f'Shipment does not exist')

        if hasattr(shipment, 'routeleg'):
            if shipment.routeleg.route.pk == self.context['view'].kwargs['route_pk']:
                raise ValidationError(f'Shipment already included in this route')
            else:
                raise ValidationError(f'Shipment already included on another route')

        if TransitState(shipment.state).value > TransitState.AWAITING_PICKUP.value:
            raise ValidationError(f'Shipment already picked up, cannot add to route')

        if shipment.device:
            raise ValidationError(f'Shipment has device associated, cannot add to route')

        return shipment.pk

    def validate(self, attrs):
        route = Route.objects.get(pk=self.context['view'].kwargs['route_pk'])
        if route.routeleg_set.filter(shipment__state__gt=TransitState.AWAITING_PICKUP.value).exists():
            raise ValidationError(f'Cannot add shipment to route after transit has begun')
        return attrs

    def create(self, validated_data):
        try:
            route = Route.objects.get(pk=self.context['view'].kwargs['route_pk'])
            return RouteLeg.objects.create(
                route=route,
                shipment_id=validated_data['shipment_id'],
                sequence=route.get_next_leg_sequence(),
            )
        except IntegrityError as exc:
            raise ValidationError(f'{exc}')
