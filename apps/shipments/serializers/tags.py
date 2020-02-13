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
from rest_framework_json_api import serializers

from ..models import ShipmentTag


class ShipmentTagSerializer(serializers.ModelSerializer):
    definition = serializers.HStoreField(
        child=serializers.RegexField(
            regex=r'^\S*$',
            max_length=25,
            error_messages={'invalid': 'Space(s) not allowed within definition fields'}
        )
    )

    class Meta:
        model = ShipmentTag
        fields = '__all__'

    def validate_definition(self, definition):
        """
        Apparently the model field validation is not run on HStoreField
        """
        ShipmentTag.definition_validator(definition)

        return definition

class ShipmentTagCreateSerializer(ShipmentTagSerializer):

    class Meta:
        model = ShipmentTag
        if settings.PROFILES_ENABLED:
            exclude = ('shipment', 'user_id', )
        else:
            exclude = ('shipment', )
