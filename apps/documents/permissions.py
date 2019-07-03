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

import logging
from rest_framework import permissions

from apps.shipments.models import Shipment

from apps.permissions import check_has_shipment_owner_access


LOG = logging.getLogger('transmission')


class UserHasPermission(permissions.BasePermission):
    """
    Custom permission to only allow owners of an object to edit it
    """

    def has_object_permission(self, request, view, obj):
        shipment = obj.shipment

        return check_has_shipment_owner_access(request, shipment)

    def has_permission(self, request, view):

        shipment_id = view.kwargs.get('shipment_pk', None)
        if not shipment_id:
            # The document's views are only accessible via nested routes
            return False
        try:
            shipment = Shipment.objects.get(id=shipment_id)
        except Shipment.DoesNotExist:
            LOG.warning(f'User: {request.user}, is trying to access documents of not found shipment: {shipment_id}')
            return False

        return check_has_shipment_owner_access(request, shipment)


class UserHasCsvFilePermission(permissions.BasePermission):

    def has_object_permission(self, request, view, obj):
        return obj.updated_by == request.user.id
