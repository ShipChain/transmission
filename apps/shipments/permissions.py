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

from django.core.exceptions import ObjectDoesNotExist
from rest_framework import permissions

from apps.permissions import has_owner_access, check_has_shipment_owner_access, shipment_exists, check_permission_link
from .models import PermissionLink


class IsShipmentOwner(permissions.BasePermission):
    """
    Custom permission to allow only the owner or a wallet owner to interact with a shipment's permission link
    """

    def has_object_permission(self, request, view, obj):
        shipment_id = view.kwargs.get('shipment_pk', None)
        if shipment_id:
            shipment = shipment_exists(shipment_id)
            if not shipment:
                return False
            return check_has_shipment_owner_access(request, shipment)
        return False

    def has_permission(self, request, view):
        shipment_id = view.kwargs.get('shipment_pk', None)
        if shipment_id:
            shipment = shipment_exists(shipment_id)
            if not shipment:
                return False
            return check_has_shipment_owner_access(request, shipment)
        return False


class IsListenerOwner(permissions.BasePermission):
    """
    Custom permission to only allow owners of an object to edit it
    """

    def has_permission(self, request, view):
        shipment_id = view.kwargs.get('shipment_pk', None)

        if shipment_id:
            shipment = shipment_exists(shipment_id)
            if not shipment:
                return False
            return check_permission_link(request, shipment)

        # Transactions are still accessible on their own endpoint
        return request.user.is_authenticated

    def has_object_permission(self, request, view, obj):
        # Permissions are allowed to anyone who owns a shipment listening to this job
        for shipment in obj.listeners.filter(Model='shipments.Shipment'):
            if has_owner_access(request, shipment):
                return True
        return False


class IsOwnerOrShared(permissions.IsAuthenticated):
    """
    Custom permission to allow users with a unique link to access a shipment anonymously
    """
    def has_permission(self, request, view):

        permission_link = request.query_params.get('permission_link', None)
        shipment_pk = view.kwargs.get('pk', None) or view.kwargs.get('shipment_pk', None)

        # The shipments can only be accessible via permission links only on shipment-detail endpoints
        if permission_link and not shipment_pk:
            return False

        permission_obj = None
        if permission_link:
            try:
                permission_obj = PermissionLink.objects.get(pk=permission_link)
            except ObjectDoesNotExist:
                pass
        if (not permission_obj or not permission_obj.is_valid) and not shipment_pk:
            return super(IsOwnerOrShared, self).has_permission(request, view)

        if shipment_pk:
            shipment = shipment_exists(shipment_pk)
            if not shipment:
                return False
            return check_permission_link(request, shipment)
        return request.user and request.user.is_authenticated

    def has_object_permission(self, request, view, obj):
        if check_has_shipment_owner_access(request, obj):
            return True

        if 'permission_link' not in request.query_params:
            return check_has_shipment_owner_access(request, obj)

        return check_permission_link(request, obj)


class IsAuthenticatedOrDevice(permissions.IsAuthenticated):
    """
    Custom permission to allow users to access tracking data, or update if its a device
    """
    def has_permission(self, request, view):
        if request.method == 'POST':
            # Device authentication is handled during tracking data validation
            return True

        return super(IsAuthenticatedOrDevice, self).has_permission(request, view)
