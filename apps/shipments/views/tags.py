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
from rest_framework import permissions
from shipchain_common import mixins
from shipchain_common.permissions import HasViewSetActionPermissions
from shipchain_common.viewsets import ActionConfiguration, ConfigurableGenericViewSet

from apps.permissions import ShipmentExists, IsNestedOwner
from ..models import ShipmentTag, AccessRequest, PermissionLevel, Endpoints
from ..serializers import ShipmentTagSerializer, ShipmentTagCreateSerializer, ShipmentTagUpdateSerializer

READ_PERMISSIONS = ((permissions.IsAuthenticated,
                     ShipmentExists,
                     HasViewSetActionPermissions,
                     IsNestedOwner | AccessRequest.permission(Endpoints.tags, PermissionLevel.READ_ONLY),)
                    if settings.PROFILES_ENABLED else (permissions.AllowAny, ShipmentExists, ))
WRITE_PERMISSIONS = ((permissions.IsAuthenticated,
                     ShipmentExists,
                     HasViewSetActionPermissions,
                     IsNestedOwner | AccessRequest.permission(Endpoints.tags, PermissionLevel.READ_WRITE), )
                     if settings.PROFILES_ENABLED else (permissions.AllowAny, ShipmentExists, ))


class ShipmentTagViewSet(mixins.ConfigurableCreateModelMixin,
                         mixins.ConfigurableDestroyModelMixin,
                         mixins.ConfigurableUpdateModelMixin,
                         ConfigurableGenericViewSet):

    queryset = ShipmentTag.objects.all()

    serializer_class = ShipmentTagSerializer

    permission_classes = READ_PERMISSIONS

    configuration = {
        'create': ActionConfiguration(
            request_serializer=ShipmentTagCreateSerializer,
            permission_classes=WRITE_PERMISSIONS
        ),
        'update': ActionConfiguration(
            request_serializer=ShipmentTagUpdateSerializer,
            permission_classes=WRITE_PERMISSIONS
        )
    }
