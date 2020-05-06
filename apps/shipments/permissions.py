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
from django.db.models import Q
from rest_framework import permissions

from apps.permissions import IsShipmentOwnerMixin, IsShipperMixin, IsModeratorMixin, IsCarrierMixin
from .models import Shipment, PermissionLink
from ..utils import retrieve_profiles_wallet_ids


class IsSharedShipmentMixin:

    @staticmethod
    def has_valid_permission_link(request, shipment):
        permission_link = PermissionLink.objects.filter(pk=request.query_params.get('permission_link')).first()
        if permission_link:
            if not permission_link.is_valid:
                return False

            return shipment.id == permission_link.shipment.id
        return False


class IsAuthenticatedOrDevice(permissions.IsAuthenticated):
    """
    Custom permission to allow users to access tracking data, or update if its a device
    """
    def has_permission(self, request, view):
        if request.method == 'POST':
            # Device authentication is handled during tracking data validation
            return True

        return super(IsAuthenticatedOrDevice, self).has_permission(request, view)


class IsOwnerOrShared(IsShipmentOwnerMixin,
                      IsShipperMixin,
                      IsCarrierMixin,
                      IsModeratorMixin,
                      IsSharedShipmentMixin,
                      permissions.IsAuthenticated):
    def has_permission(self, request, view):
        # If nested route, we need to call has_object_permission on the Shipment
        is_authenticated = super().has_permission(request, view)
        has_permission_link = request.query_params.get('permission_link')
        nested_shipment = view.kwargs.get('shipment_pk')
        nested_device = view.kwargs.get('device_pk')

        if not is_authenticated and not has_permission_link:
            # Unauthenticated requests must have a permission_link
            return False

        if nested_shipment:
            # Nested routes do not call has_object_permission for the parent Shipment,
            # so we must check object permissions here
            shipment = Shipment.objects.get(id=nested_shipment)
            return self.has_object_permission(request, view, shipment)

        if nested_device:
            # Nested device routes need to be ensured that they have a shipment associated with the device
            shipment = Shipment.objects.filter(device_id=nested_device).first()
            return shipment and self.has_object_permission(request, view, shipment)

        # Not nested, has_object_permission will handle the permission link check
        return is_authenticated or has_permission_link

    def has_object_permission(self, request, view, obj):
        return self.is_shipment_owner(request, obj) or \
           self.has_valid_permission_link(request, obj) or \
           self.has_shipper_permission(request, obj) or \
           self.has_carrier_permission(request, obj) or \
           self.has_moderator_permission(request, obj)


class IsOwnerShipperCarrierModerator(IsShipmentOwnerMixin,
                                     IsShipperMixin,
                                     IsCarrierMixin,
                                     IsModeratorMixin,
                                     permissions.IsAuthenticated):
    """
    Custom permission to allow only Owners, Shipper, Carrier and Moderator
    to modify a shipment
    """

    def has_permission(self, request, view):
        # If nested route, we need to call has_object_permission on the Shipment
        is_authenticated = super().has_permission(request, view)
        nested_shipment = view.kwargs.get('shipment_pk')

        if not is_authenticated:
            return False

        if nested_shipment:
            # Nested routes do not call has_object_permission for the parent Shipment,
            # so we must check object permissions here
            shipment = Shipment.objects.get(id=view.kwargs.get('shipment_pk'))
            return self.has_object_permission(request, view, shipment)

        # Not nested, has_object_permission will handle permission checks
        return is_authenticated

    def has_object_permission(self, request, view, obj):
        return self.is_shipment_owner(request, obj) or \
           self.has_shipper_permission(request, obj) or \
           self.has_carrier_permission(request, obj) or \
           self.has_moderator_permission(request, obj)


class IsListenerOwner(IsOwnerOrShared):
    """
    Custom permission to only allow owners of an object to edit it
    """

    def has_object_permission(self, request, view, obj):
        # Permissions are allowed to anyone who owns a shipment listening to this job
        shipment = obj.shipment if hasattr(obj, 'shipment') else obj
        return self.is_shipment_owner(request, shipment) or self.has_valid_permission_link(request, shipment)


def shipment_list_wallets_filter(request, nested=False):
    wallet_ids = retrieve_profiles_wallet_ids(request)
    queries = Q()
    for field in ('carrier', 'shipper', 'moderator'):
        queries |= Q(**{f'{"shipment__" if nested else ""}{field}_wallet_id__in': wallet_ids})

    return queries
