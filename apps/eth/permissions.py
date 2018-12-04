from rest_framework import permissions
from django.conf import settings


class IsOwner(permissions.BasePermission):
    """
    Custom permission to only allow owners of an object to edit it
    """

    def has_object_permission(self, request, view, obj):

        # Permissions are only allowed to the owner of the shipment.
        for shipment in obj.listeners.filter(Model='shipments.Shipment'):
            if shipment.owner_id == request.user.id:
                return True
        return False


class ProfilesRequest(permissions.BasePermission):
    def has_permission(self, request, view):
        if settings.PROFILES_ENABLED:
            return True

        return False
