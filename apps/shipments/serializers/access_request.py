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

from enumfields.drf import EnumSupportSerializerMixin
from rest_framework_json_api import serializers
from shipchain_common.utils import UpperEnumField

from apps.permissions import get_user
from ..models import AccessRequest, PermissionLevel


class AccessRequestSerializer(EnumSupportSerializerMixin, serializers.ModelSerializer):
    shipment_permission = UpperEnumField(PermissionLevel, lenient=True, ints_as_names=True, required=False)
    tags_permission = UpperEnumField(PermissionLevel, lenient=True, ints_as_names=True, required=False)
    documents_permission = UpperEnumField(PermissionLevel, lenient=True, ints_as_names=True, required=False)
    notes_permission = UpperEnumField(PermissionLevel, lenient=True, ints_as_names=True, required=False)
    tracking_permission = UpperEnumField(PermissionLevel, lenient=True, ints_as_names=True, required=False)
    telemetry_permission = UpperEnumField(PermissionLevel, lenient=True, ints_as_names=True, required=False)

    class Meta:
        model = AccessRequest
        fields = '__all__'


class AccessRequestCreateSerializer(AccessRequestSerializer):
    class Meta:
        model = AccessRequest
        if settings.PROFILES_ENABLED:
            exclude = ('requester_id', 'shipment',)
        else:
            exclude = ('shipment', )

    def create(self, validated_data):
        validated_data['shipment_id'] = self.context['view'].kwargs['shipment_pk']

        if settings.PROFILES_ENABLED:
            validated_data['requester_id'] = get_user(self.context['request'])[0]

        return AccessRequest.objects.create(**validated_data)
