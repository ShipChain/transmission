import logging
from django.conf import settings
from rest_framework import permissions, status

from apps.shipments.models import Shipment
from apps.authentication import get_jwt_from_request
from apps.permissions import has_owner_access


LOG = logging.getLogger('transmission')

PROFILES_URL = f'{settings.PROFILES_URL}/api/v1/wallet'


class UserHasPermission(permissions.BasePermission):
    """
    Custom permission to only allow owners of an object to edit it
    """

    def has_object_permission(self, request, view, obj):
        shipment = obj.shipment

        return has_owner_access(request, obj) or has_owner_access(request, shipment) or \
            self.is_shipper(request, shipment) or self.is_carrier(request, shipment) or \
            self.is_moderator(request, shipment)

    def has_permission(self, request, view):

        shipment_id = request.parser_context['kwargs'].get('shipment_pk', None)
        if not shipment_id:
            # The document's views are only accessible via nested route
            return False
        try:
            shipment = Shipment.objects.get(id=shipment_id)
        except Shipment.DoesNotExist:
            LOG.warning(f'User: {request.user}, is trying to access documents of not found shipment: {shipment_id}')
            return False

        return has_owner_access(request, shipment) or self.is_shipper(request, shipment) or \
            self.is_carrier(request, shipment) or self.is_moderator(request, shipment)

    def is_carrier(self, request, shipment):
        """
        Custom permission for carrier documents management access
        """
        response = settings.REQUESTS_SESSION.get(f'{PROFILES_URL}/{shipment.carrier_wallet_id}/?is_active',
                                                 headers={'Authorization': f'JWT {get_jwt_from_request(request)}'})

        return response.status_code == status.HTTP_200_OK

    def is_moderator(self, request, shipment):
        """
        Custom permission for moderator documents management access
        """
        if shipment.moderator_wallet_id:
            response = settings.REQUESTS_SESSION.get(f'{PROFILES_URL}/{shipment.moderator_wallet_id}/?is_active',
                                                     headers={'Authorization': f'JWT {get_jwt_from_request(request)}'})

        return shipment.moderator_wallet_id and response.status_code == status.HTTP_200_OK

    def is_shipper(self, request, shipment):
        """
        Custom permission for shipper documents management access
        """
        response = settings.REQUESTS_SESSION.get(f'{PROFILES_URL}/{shipment.shipper_wallet_id}/?is_active',
                                                 headers={'Authorization': f'JWT {get_jwt_from_request(request)}'})

        return response.status_code == status.HTTP_200_OK
