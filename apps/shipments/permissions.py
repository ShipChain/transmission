from datetime import datetime, timezone

from django.core.exceptions import ObjectDoesNotExist
from rest_framework import permissions

from apps.permissions import has_owner_access
from .models import PermissionLink, Shipment


class IsShipmentOwner(permissions.BasePermission):
    """
    Custom permission to only allow owners of an object to edit it (for use in related querysets)
    """
    def has_permission(self, request, view):
        shipment = Shipment.objects.get(pk=view.kwargs['shipment_pk'])
        return has_owner_access(request, shipment)


class IsListenerOwner(permissions.BasePermission):
    """
    Custom permission to only allow owners of an object to edit it
    """
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
        return (super(IsOwnerOrShared, self).has_permission(request, view) or
                ('permission_link' in request.query_params and request.query_params['permission_link']))

    def has_object_permission(self, request, view, obj):
        if request.user.is_authenticated and has_owner_access(request, obj):
            return True
        if 'permission_link' in request.query_params and request.query_params['permission_link']:
            try:
                permission_link = PermissionLink.objects.get(pk=request.query_params['permission_link'])
            except ObjectDoesNotExist:
                return False
            if permission_link.expiration_date:
                return (datetime.now(timezone.utc) < permission_link.expiration_date
                        and obj.pk == permission_link.shipment.pk and request.method == 'GET')
            return obj.pk == permission_link.shipment.pk and request.method == 'GET'
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
