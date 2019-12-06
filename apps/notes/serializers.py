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


from django.conf import settings

from rest_framework_json_api import serializers

from apps.shipments.models import Shipment
from .models import ShipmentNote


class ShipmentNoteSerializer(serializers.ModelSerializer):

    class Meta:
        model = ShipmentNote
        exclude = ('shipment', )


class ShipmentNoteCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = ShipmentNote
        if settings.PROFILES_ENABLED:
            exclude = ('author_id', 'shipment', )
        else:
            exclude = ('shipment', )

    def create(self, validated_data):
        if settings.PROFILES_ENABLED:
            return ShipmentNote.objects.create(**validated_data)

        try:
            # We ensure that the provided shipment exists when profiles is disabled
            Shipment.objects.get(id=self.context['shipment_id'])
        except Shipment.DoesNotExist:
            raise serializers.ValidationError('Invalid shipment provided')
        return ShipmentNote.objects.create(**validated_data, **self.context)
