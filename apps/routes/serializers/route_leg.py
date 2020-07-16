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

from apps.routes.models import RouteLeg
from apps.shipments.models import Shipment, TransitState
from apps.shipments.permissions import IsOwnerOrShared


class RouteLegInfoSerializer(serializers.ModelSerializer):

    class Meta:
        model = RouteLeg
        fields = ('shipment_id', '_order')


class RouteLegCreateSerializer(serializers.ModelSerializer):
    shipment_id = serializers.UUIDField()

    class Meta:
        model = RouteLeg
        fields = ('shipment_id',)

    def validate_shipment_id(self, data):
        shipment = Shipment.objects.filter(pk=data).first()

        if not shipment or \
                not IsOwnerOrShared().has_object_permission(self.context['request'], self.context['view'], shipment):
            raise ValidationError('Shipment does not exist')

        if hasattr(shipment, 'routeleg'):
            if shipment.routeleg.route.pk == self.context['view'].kwargs['route_pk']:
                raise ValidationError('Shipment already included in this route')
            else:
                raise ValidationError('Shipment already included on another route')

        if TransitState(shipment.state).value > TransitState.AWAITING_PICKUP.value:
            raise ValidationError('Shipment already picked up, cannot add to route')

        if shipment.device:
            raise ValidationError('Shipment has device associated, cannot add to route')

        return shipment.pk

    def validate(self, attrs):
        if RouteLeg.objects.filter(route_id=self.context['view'].kwargs['route_pk'],
                                   shipment__state__gt=TransitState.AWAITING_PICKUP.value,
                                   ).exists():
            raise ValidationError('Cannot add shipment to route after transit has begun')
        return attrs

    def create(self, validated_data):
        try:
            return RouteLeg.objects.create(
                route_id=self.context['view'].kwargs['route_pk'],
                shipment_id=validated_data['shipment_id'],
            )
        except IntegrityError as exc:
            raise ValidationError(f'{exc}')
