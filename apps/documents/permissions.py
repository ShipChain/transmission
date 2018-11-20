import datetime
from rest_framework import permissions


class IsOwner(permissions.BasePermission):
    """
    Custom permission to only allow owners of an object to edit it
    """

    def has_object_permission(self, request, view, obj):

        return obj.owner_id == request.user.id


class PeriodPermission(permissions.BasePermission):
    """
    Custom permission for creating and accessing documents after delivery date
    """
    def has_object_permission(self, request, view, obj):

        date_now = datetime.datetime.now()
        delivery_actual = obj.shipment.delivery_actual

        if delivery_actual:
            return date_now < delivery_actual.replace(tzinfo=None) + datetime.timedelta(days=10)

        return True
