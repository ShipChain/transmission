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

from django.conf import settings
from rest_framework.validators import UniqueTogetherValidator
from rest_framework_json_api import serializers

from apps.permissions import get_owner_id
from ..models import ShipmentTag


class ShipmentTagSerializer(serializers.ModelSerializer):

    class Meta:
        model = ShipmentTag
        fields = '__all__'


class ShipmentTagCreateSerializer(ShipmentTagSerializer):
    shipment_id = serializers.CharField(required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.initial_data = self.initial_data.copy()
        self.initial_data.update(shipment_id=self.context['view'].kwargs['shipment_pk'])

        if settings.PROFILES_ENABLED:
            self.initial_data.update(owner_id=get_owner_id(self.context['request']))

    class Meta:
        model = ShipmentTag
        fields = ('owner_id', 'shipment_id', 'tag_type', 'tag_value', )
        validators = [
            UniqueTogetherValidator(
                queryset=ShipmentTag.objects.all(),
                fields=['shipment_id', 'tag_type', 'tag_value'],
                message='This shipment already has a tag with the provided [tag_type] and [tag_value].'
            )
        ]
