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

from ..models import ShipmentTag


class ShipmentTagSerializer(serializers.ModelSerializer):

    class Meta:
        model = ShipmentTag
        fields = '__all__'


class ShipmentTagCreateSerializer(ShipmentTagSerializer):
    _unique_together_validator = UniqueTogetherValidator(queryset=ShipmentTag.objects.all(),
                                                         fields=('shipment_id', 'tag_type', 'tag_value'))

    class Meta:
        model = ShipmentTag
        if settings.PROFILES_ENABLED:
            exclude = ('shipment', 'user_id', )
        else:
            exclude = ('shipment', )

    def validate(self, attrs):
        """
        This method aims at validate the Unique Together constrain on tag_type, tag_value
        and shipment_id(foreign key) attributes.
        This to avoid having multiple tags on a shipment with same definition.
        """

        attrs['shipment_id'] = self.context['view'].kwargs.get('shipment_pk')

        self._unique_together_validator.instance = self.instance
        self._unique_together_validator(attrs)

        return attrs
