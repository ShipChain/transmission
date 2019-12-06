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

import logging

from django.conf import settings

from rest_framework_json_api import serializers

from apps.shipments.models import Shipment
from .models import ShipmentNote

LOG = logging.getLogger('transmission')


class ShipmentNoteSerializer(serializers.Serializer):

    class Meta:
        model = ShipmentNote
        if settings.PROFILES_ENABLED:
            exclude = ('author_id', 'shipment', )
        else:
            exclude = ('shipment', )

    def create(self, validated_data):
        if not settings.PROFILES_ENABLED:
            # Check specific to profiles disabled
            try:
                Shipment.objects.get(id=self.context['shipment_id'])
            except Shipment.DoesNotExist:
                raise serializers.ValidationError('Invalid shipment provided')
            return ShipmentNote.objects.create(**validated_data, **self.context)

        return ShipmentNote.objects.create(**validated_data)
