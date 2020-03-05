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

from apps.permissions import get_user, get_organization_name, get_requester_username
from ..models import ShipmentNote


class ShipmentNoteSerializer(serializers.ModelSerializer):

    class Meta:
        model = ShipmentNote
        fields = '__all__'


class ShipmentNoteCreateSerializer(ShipmentNoteSerializer):
    class Meta:
        model = ShipmentNote
        if settings.PROFILES_ENABLED:
            exclude = ('user_id', 'shipment', 'username', 'organization_name', )
        else:
            exclude = ('shipment', )

    def create(self, validated_data):
        validated_data['shipment_id'] = self.context['view'].kwargs['shipment_pk']

        if settings.PROFILES_ENABLED:
            validated_data['organization_name'] = get_organization_name(self.context['request'])
            validated_data['user_id'] = get_user(self.context['request'])[0]
            validated_data['username'] = get_requester_username(self.context['request']).split('@')[0]

        return ShipmentNote.objects.create(**validated_data)
