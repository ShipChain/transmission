import datetime

from django.conf import settings
from rest_framework import permissions, status


PROFILES_URL = f'{settings.PROFILES_URL}/api/v1/wallet/'


class UserHasPermission(permissions.BasePermission):
    """
    Custom permission to only allow owners of an object to edit it
    """

    def has_object_permission(self, request, view, obj):

        def is_carrier():
            """
            Custom permission for carrier documents management access
            """
            response = settings.REQUESTS_SESSION.get(f'{PROFILES_URL}/{obj.shipment.carrier_wallet_id}/',
                                                     headers={'Authorization': 'JWT {}'.format(request.auth.decode())})

            if response.status_code != status.HTTP_200_OK:
                return False
            return True

        def is_moderator():
            """
            Custom permission for moderator documents management access
            """
            response = settings.REQUESTS_SESSION.get(f'{PROFILES_URL}/{obj.shipment.moderator_wallet_id}/',
                                                     headers={'Authorization': 'JWT {}'.format(request.auth.decode())})

            if response.status_code != status.HTTP_200_OK:
                return False
            return True

        def is_shipper():
            """
            Custom permission for shipper documents management access
            """
            response = settings.REQUESTS_SESSION.get(f'{PROFILES_URL}/{obj.shipment.shipper_wallet_id}/',
                                                     headers={'Authorization': 'JWT {}'.format(request.auth.decode())})

            if response.status_code != status.HTTP_200_OK:
                return False
            return True

        def is_owner():
            return obj.owner_id == request.user.id

        return is_owner() or is_carrier() or is_moderator() or is_shipper()


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
