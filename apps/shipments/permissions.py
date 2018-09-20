from rest_framework import permissions


class IsOwner(permissions.BasePermission):
    """
    Custom permission to only allow owners of an object to edit it
    """

    def has_object_permission(self, request, view, obj):

        # Permissions are only allowed to the owner of the shipment.
        return obj.owner_id == request.user.id


class IsUserOrDevice(permissions.BasePermission):
    """
    Custom permission to allow users to access tracking data, or update if its a device
    """
    def has_permission(self, request, view):
        if request.method == 'POST':
            # Device authentication is handled during tracking data validation
            return True

        return request.user and request.user.is_authenticated
