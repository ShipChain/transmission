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

from apps.permissions import get_user, owner_access_filter
from ..models import AccessRequest, PermissionLevel, Shipment

PERMISSION_FIELD_LIST = ('shipment_permission', 'tags_permission', 'documents_permission', 'notes_permission',
                         'tracking_permission', 'telemetry_permission')


def read_only_validator(value):
    if value == PermissionLevel.READ_WRITE:
        raise serializers.ValidationError('Cannot request write access to this field')


class AccessRequestPermissionValidator:
    # requires_context = True  TODO: this can be used in DRF 3.12 to remove the set_context call
    def __init__(self):
        self.field_name = None
        self.serializer = None

    def set_context(self, serializer):
        self.field_name = serializer.field_name
        self.serializer = serializer.parent

    def __call__(self, value):
        instance = getattr(self.serializer, 'instance', None)
        approved = instance.approved if instance else self.serializer.initial_data.get('approved', None)
        value_changed = getattr(instance, self.field_name) != value if instance else False

        if approved:
            raise serializers.ValidationError('Cannot modify the permission level of an approved access request')
        if value_changed:
            (user_id, _) = get_user(self.serializer.context['request'])
            if str(instance.requester_id) != user_id:
                raise serializers.ValidationError('Only the requester can modify permissions in a pending or denied '
                                                  'access request')

            if approved is False:
                # Modifying a denied access request changes it back to pending
                instance.approved = None


class AccessRequestSerializer(EnumSupportSerializerMixin, serializers.ModelSerializer):
    shipment_permission = UpperEnumField(PermissionLevel, lenient=True, ints_as_names=True, required=False,
                                         validators=(AccessRequestPermissionValidator(),))
    tags_permission = UpperEnumField(PermissionLevel, lenient=True, ints_as_names=True, required=False,
                                     validators=(AccessRequestPermissionValidator(),))
    documents_permission = UpperEnumField(PermissionLevel, lenient=True, ints_as_names=True, required=False,
                                          validators=(AccessRequestPermissionValidator(),))
    notes_permission = UpperEnumField(PermissionLevel, lenient=True, ints_as_names=True, required=False,
                                      validators=(AccessRequestPermissionValidator(),))
    tracking_permission = UpperEnumField(PermissionLevel, lenient=True, ints_as_names=True, required=False,
                                         validators=(AccessRequestPermissionValidator(), read_only_validator))
    telemetry_permission = UpperEnumField(PermissionLevel, lenient=True, ints_as_names=True, required=False,
                                          validators=(AccessRequestPermissionValidator(), read_only_validator))

    class Meta:
        model = AccessRequest
        fields = '__all__'

    def validate_approved(self, approved):
        if settings.PROFILES_ENABLED:
            if approved and not Shipment.objects.filter(owner_access_filter(self.context['request'])).exists():
                raise serializers.ValidationError('User does not have access to approve this access request')

        return approved

    def validate(self, attrs):
        if attrs.get('approved', None):
            if not all(perm in attrs for perm in PERMISSION_FIELD_LIST):
                raise serializers.ValidationError('Full list of permissions must be passed in request for approval')

        # Validate that request does not have ALL PermissionLevel.NONE
        current_permissions = {perm: getattr(self.instance, perm) if self.instance else PermissionLevel.NONE
                               for perm in PERMISSION_FIELD_LIST}
        updated_permissions = {**current_permissions,
                               **{field: attrs[field] for field in attrs if field.endswith('_permission')}}

        if (updated_permissions['tags_permission'] > PermissionLevel.NONE and
                updated_permissions['shipment_permission'] == PermissionLevel.NONE):
            raise serializers.ValidationError('Cannot request to view tags without shipment read access')

        for field in updated_permissions:
            if updated_permissions[field] != PermissionLevel.NONE:
                return attrs
        raise serializers.ValidationError("Access requests must contain at least one requested permission")


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
