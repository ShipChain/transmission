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

from django.db import models
from enum import auto
from enumfields import Enum, EnumField

from .shipment import Shipment


class PermissionLevel(Enum):
    NONE = auto()
    READ_ONLY = auto()
    READ_WRITE = auto()

    class Labels:
        NONE = 'NONE'
        READ_ONLY = 'READ_ONLY'
        READ_WRITE = 'READ_WRITE'

class AccessRequest(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    updated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)
    requester_id = models.UUIDField(null=False)

    shipment = models.ForeignKey(Shipment, on_delete=models.CASCADE)

    shipment_permission = EnumField(PermissionLevel, default=PermissionLevel.NONE)
    tags_permission = EnumField(PermissionLevel, default=PermissionLevel.NONE)
    documents_permission = EnumField(PermissionLevel, default=PermissionLevel.NONE)
    notes_permission = EnumField(PermissionLevel, default=PermissionLevel.NONE)
    tracking_permission = EnumField(PermissionLevel, default=PermissionLevel.NONE)
    telemetry_permission = EnumField(PermissionLevel, default=PermissionLevel.NONE)

    approved = models.NullBooleanField(default=None)
    approved_at = models.DateTimeField(default=None, null=True)
    approved_by = models.UUIDField(default=None, null=True)

    class Meta:
        ordering = ('created_at',)
