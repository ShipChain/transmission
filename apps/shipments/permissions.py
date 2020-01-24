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

from apps.permissions import shipment_exists, IsShipmentOwnerMixin, IsShipperMixin, IsModeratorMixin, IsCarrierMixin
from .models import PermissionLink


class IsSharedShipmentMixin:

    @staticmethod
    def has_valid_permission_link(request, shipment):
        permission_link = request.query_params.get('permission_link')
        if permission_link:
            try:
                permission_obj = PermissionLink.objects.get(pk=permission_link)
            except ObjectDoesNotExist:
                return False

            if not permission_obj.is_valid:
                return False

            return shipment.id == permission_obj.shipment.id
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
                      permissions.BasePermission):
    """
    Custom permission to allow users with a unique link to access a shipment anonymously
    """

    def has_permission(self, request, view):
        shipment_pk = view.kwargs.get('pk') or view.kwargs.get('shipment_pk')
        permission_link = request.query_params.get('permission_link')
        shipment = shipment_exists(shipment_pk)

        if permission_link and not shipment:
            # Shipment accessible via permission link only on nested route
            return False

        if shipment:
            return self.is_shipment_owner(request, shipment) or \
               self.has_valid_permission_link(request, shipment) or \
               self.has_shipper_permission(request, shipment) or \
               self.has_carrier_permission(request, shipment) or \
               self.has_moderator_permission(request, shipment)

        if shipment_pk:
            return False

        return True

    def has_object_permission(self, request, view, obj):
        return self.is_shipment_owner(request, obj) or \
           self.has_valid_permission_link(request, obj) or \
           self.has_shipper_permission(request, obj) or \
           self.has_carrier_permission(request, obj) or \
           self.has_moderator_permission(request, obj)


class HasShipmentUpdatePermission(IsShipmentOwnerMixin,
                                  IsShipperMixin,
                                  IsCarrierMixin,
                                  IsModeratorMixin,
                                  permissions.BasePermission):
    """
    Custom permission to allow only Owners, Shipper, Carrier and Moderator
    to modify a shipment
    """

    def has_permission(self, request, view):
        shipment_pk = view.kwargs.get('pk') or view.kwargs.get('shipment_pk')
        shipment = shipment_exists(shipment_pk)

        if shipment:
            return self.is_shipment_owner(request, shipment) or \
               self.has_shipper_permission(request, shipment) or \
               self.has_carrier_permission(request, shipment) or \
               self.has_moderator_permission(request, shipment)

        if shipment_pk:
            return False

        return False


class IsListenerOwner(IsShipmentOwnerMixin,
                      IsSharedShipmentMixin,
                      IsShipperMixin,
                      IsCarrierMixin,
                      IsModeratorMixin,
                      permissions.BasePermission):
    """
    Custom permission to only allow owners of an object to edit it
    """

    def has_permission(self, request, view):
        shipment_id = view.kwargs.get('shipment_pk')

        if shipment_id:
            shipment = shipment_exists(shipment_id)
            if not shipment:
                return False

            return self.is_shipment_owner(request, shipment) or \
                self.has_valid_permission_link(request, shipment) or \
                self.has_shipper_permission(request, shipment) or \
                self.has_carrier_permission(request, shipment) or \
                self.has_moderator_permission(request, shipment)

        # Transactions are still accessible on their own endpoint
        return request.user.is_authenticated

    def has_object_permission(self, request, view, obj):
        # Permissions are allowed to anyone who owns a shipment listening to this job
        return self.is_shipment_owner(request, obj.shipment)
