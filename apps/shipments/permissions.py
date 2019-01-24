from datetime import datetime, timezone
from rest_framework import permissions
from .models import PermissionLink, Shipment


class IsOwner(permissions.BasePermission):
    """
    Custom permission to only allow owners of an object to edit it
    """

    def has_object_permission(self, request, view, obj):

        # Permissions are only allowed to the owner of the shipment.
        return obj.owner_id == request.user.id


class IsShipmentOwner(permissions.BasePermission):
    """
    Custom permission to only allow owners of an object to edit it
    """

    def has_permission(self, request, view):
        shipment = Shipment.objects.get(pk=view.kwargs['shipment_pk'])

        # Permissions are only allowed to the owner of the shipment.
        return shipment.owner_id == request.user.id


#pylint:disable=inconsistent-return-statements
class IsSharedOrOwner(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        if obj.owner_id == request.user.id:
            return True
        if 'permission_link' in request.query_params and request.query_params['permission_link']:
            permission_link = PermissionLink.objects.get(pk=request.query_params['permission_link'])
            if permission_link.expiration_date:
                return (datetime.now(timezone.utc) < permission_link.expiration_date
                        and obj.pk == permission_link.shipment.pk and request.method == 'GET')
            return obj.pk == permission_link.shipment.pk and request.method == 'GET'
        return False


class IsUserOrDevice(permissions.BasePermission):
    """
    Custom permission to allow users to access tracking data, or update if its a device
    """
    def has_permission(self, request, view):
        if request.method == 'POST':
            # Device authentication is handled during tracking data validation
            return True

        return request.user and request.user.is_authenticated
