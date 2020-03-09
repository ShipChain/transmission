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
from django.core.exceptions import ValidationError
from rest_framework_json_api import serializers

from apps.permissions import get_owner_id
from ..models import ShipmentTag


class ShipmentTagSerializer(serializers.ModelSerializer):

    class Meta:
        model = ShipmentTag
        fields = '__all__'


class ShipmentTagCreateSerializer(ShipmentTagSerializer):

    class Meta:
        model = ShipmentTag
        if settings.PROFILES_ENABLED:
            exclude = ('shipment', 'owner_id', )
        else:
            exclude = ('shipment', )

    def validate(self, attrs):

        attrs['shipment_id'] = self.context['view'].kwargs.get('shipment_pk')
        if settings.PROFILES_ENABLED:
            attrs['owner_id'] = get_owner_id(self.context['request'])

        try:
            ShipmentTag(**attrs).validate_unique()
        except ValidationError:
            raise serializers.ValidationError(f'This shipment already has a tag with, `tag_type: {attrs["tag_type"]}` '
                                              f'and `tag_value: {attrs["tag_value"]}`.')

        return attrs
