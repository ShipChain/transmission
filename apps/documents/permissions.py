from django.conf import settings
from rest_framework import permissions, status
from apps.authentication import get_jwt_from_request


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
                                                     headers={'Authorization': get_jwt_from_request(request)})

            if response.status_code != status.HTTP_200_OK:
                return False
            return True

        def is_moderator():
            """
            Custom permission for moderator documents management access
            """
            response = settings.REQUESTS_SESSION.get(f'{PROFILES_URL}/{obj.shipment.moderator_wallet_id}/',
                                                     headers={'Authorization': get_jwt_from_request(request)})

            if response.status_code != status.HTTP_200_OK:
                return False
            return True

        def is_shipper():
            """
            Custom permission for shipper documents management access
            """
            response = settings.REQUESTS_SESSION.get(f'{PROFILES_URL}/{obj.shipment.shipper_wallet_id}/',
                                                     headers={'Authorization': get_jwt_from_request(request)})

            if response.status_code != status.HTTP_200_OK:
                return False
            return True

        def is_owner():
            return obj.owner_id == request.user.id

        return is_owner() or is_shipper() or is_carrier() or is_moderator()
