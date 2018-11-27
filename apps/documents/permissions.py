import datetime
from rest_framework import permissions


class IsOwner(permissions.BasePermission):
    """
    Custom permission to only allow owners of an object to edit it
    """

    def has_object_permission(self, request, view, obj):

        return obj.owner_id == request.user.id


class AccessPeriodPermission(permissions.BasePermission):
    """
    Custom permission for creating and accessing documents after delivery date
    """
    def has_object_permission(self, request, view, obj):

        date_now = datetime.datetime.now()
        delivery_actual = obj.shipment.delivery_actual

        if delivery_actual:
            return date_now < delivery_actual.replace(tzinfo=None) + datetime.timedelta(days=10)

        return True


class IsCarrier(permissions.BasePermission):
    """
    Custom permission for carrier documents management access
    """

    def has_object_permission(self, request, view, obj):

        return obj.shipment.load_data.carrier == request.user.id


class IsModerator(permissions.BasePermission):
    """
    Custom permission for moderator documents management access
    """

    def has_object_permission(self, request, view, obj):

        moderator = obj.shipment.load_data.moderator
        if moderator:
            return obj.shipment.load_data.moderator == request.user.id

        return True
