from rest_framework import permissions


class IsOwner(permissions.BasePermission):
    """
    Custom permission to only allow owners of an object to edit it
    """

    def has_object_permission(self, request, view, obj):

        # Permissions are allowed to anyone who owns a shipment listening to this job
        is_owner = False
        for shipment in obj.listeners.filter(Model='shipments.Shipment'):
            if shipment.owner_id == request.user.id:
                is_owner = True
        return is_owner
