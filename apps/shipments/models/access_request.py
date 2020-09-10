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
import uuid
from enum import auto, Enum as PyEnum

from django.db import models
from enumfields import Enum, EnumIntegerField
from rest_framework.permissions import BasePermission
from rest_framework_serializer_field_permissions.permissions import BaseFieldPermission

from .shipment import Shipment


class PermissionLevel(Enum):
    NONE = auto()
    READ_ONLY = auto()
    READ_WRITE = auto()

    class Labels:
        NONE = 'NONE'
        READ_ONLY = 'READ_ONLY'
        READ_WRITE = 'READ_WRITE'


class Endpoints(PyEnum):
    shipment = auto()
    tags = auto()
    documents = auto()
    notes = auto()
    tracking = auto()
    telemetry = auto()


class AccessRequest(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    updated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)
    requester_id = models.UUIDField(null=False, editable=False)

    shipment = models.ForeignKey(Shipment, on_delete=models.CASCADE, editable=False)

    shipment_permission = EnumIntegerField(PermissionLevel, default=PermissionLevel.NONE)
    tags_permission = EnumIntegerField(PermissionLevel, default=PermissionLevel.NONE)
    documents_permission = EnumIntegerField(PermissionLevel, default=PermissionLevel.NONE)
    notes_permission = EnumIntegerField(PermissionLevel, default=PermissionLevel.NONE)
    tracking_permission = EnumIntegerField(PermissionLevel, default=PermissionLevel.NONE)
    telemetry_permission = EnumIntegerField(PermissionLevel, default=PermissionLevel.NONE)

    approved = models.NullBooleanField(default=None)
    approved_at = models.DateTimeField(default=None, null=True, editable=False)
    approved_by = models.UUIDField(default=None, null=True, editable=False)

    class Meta:
        ordering = ('created_at',)

    # Permission class factory
    @staticmethod
    def permission(endpoint, permission_level):
        class AccessRequestPermission(BasePermission):
            required_permission_level = permission_level

            def has_permission(self, request, view):
                nested = view.kwargs.get('shipment_pk')
                if nested:
                    filters = {
                        'id': nested,
                        f'accessrequest__{endpoint.name}_permission__gte': self.required_permission_level,
                        'accessrequest__approved': True,
                    }
                    return Shipment.objects.filter(**filters).exists()
                return True

            def has_object_permission(self, request, view, obj):
                shipment = obj.shipment if hasattr(obj, 'shipment') else obj
                filters = {
                    f'{endpoint.name}_permission__gte': self.required_permission_level,
                    'approved': True,
                }
                return shipment.accessrequest_set.filter(**filters).exists()

        return AccessRequestPermission

    @staticmethod
    def related_field_permission(endpoint, permission_level):
        class AccessRequestFieldPermission(BaseFieldPermission):
            required_permission_level = permission_level

            def has_object_permission(self, request, obj):
                if 'AccessRequestPermission' in (getattr(request, 'authorizing_permission_class', None),
                                                 getattr(request, 'authorizing_object_permission_class', None)):
                    filters = {
                        f'{endpoint.name}_permission__gte': self.required_permission_level,
                        'approved': True,
                    }
                    return obj.accessrequest_set.filter(**filters).exists()

                # Access wasn't granted to this Shipment by an AccessRequest
                return True

        return AccessRequestFieldPermission
