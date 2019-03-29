from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from rest_framework import permissions, status

from apps.authentication import get_jwt_from_request
from apps.permissions import has_owner_access
from .models import PermissionLink, Shipment


PROFILES_URL = f'{settings.PROFILES_URL}/api/v1/wallet'


class IsShipmentOwner(permissions.BasePermission):
    """
    Custom permission to only allow owners of an object to edit it (for use in related querysets)
    """

    def has_object_permission(self, request, view, obj):
        shipment_id = request.parser_context['kwargs'].get('shipment_pk', None)

        shipment = Shipment.objects.get(id=shipment_id)

        return (has_owner_access(request, shipment) or self.is_shipper(request, shipment) or
                self.is_carrier(request, shipment) or self.is_moderator(request, shipment))

    def has_permission(self, request, view):
        shipment_id = request.parser_context['kwargs'].get('shipment_pk', None)
        if not shipment_id:
            return True

        shipment = Shipment.objects.get(id=shipment_id)

        return has_owner_access(request, shipment) or self.is_shipper(request, shipment) or \
               self.is_carrier(request, shipment) or self.is_moderator(request, shipment)

    def is_carrier(self, request, shipment):
        """
        Custom permission for carrier documents management access
        """
        response = settings.REQUESTS_SESSION.get(f'{PROFILES_URL}/{shipment.carrier_wallet_id}/?is_active',
                                                 headers={'Authorization': f'JWT {get_jwt_from_request(request)}'})

        return response.status_code == status.HTTP_200_OK and request.method in ('GET', 'PATCH')

    def is_moderator(self, request, shipment):
        """
        Custom permission for moderator documents management access
        """
        if shipment.moderator_wallet_id:
            response = settings.REQUESTS_SESSION.get(f'{PROFILES_URL}/{shipment.moderator_wallet_id}/?is_active',
                                                     headers={'Authorization': f'JWT {get_jwt_from_request(request)}'})

        return (shipment.moderator_wallet_id and response.status_code == status.HTTP_200_OK and
                request.method in ('GET', 'PATCH'))

    def is_shipper(self, request, shipment):
        """
        Custom permission for shipper documents management access
        """
        response = settings.REQUESTS_SESSION.get(f'{PROFILES_URL}/{shipment.shipper_wallet_id}/?is_active',
                                                 headers={'Authorization': f'JWT {get_jwt_from_request(request)}'})

        return response.status_code == status.HTTP_200_OK and request.method in ('GET', 'PATCH')


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

        permission_link = request.query_params.get('permission_link', None)
        shipment_pk = request.parser_context['kwargs'].get('pk', None)

        # The shipments can only be accessible via permission link only on shipment-detail endpoint
        if permission_link and not shipment_pk:
            return False

        permission_obj = None
        if permission_link:
            try:
                permission_obj = PermissionLink.objects.get(pk=permission_link)
            except ObjectDoesNotExist:
                pass
        if (not permission_obj or not permission_obj.is_valid) and not shipment_pk:
            return super(IsOwnerOrShared, self).has_permission(request, view)

        if shipment_pk:
            try:
                shipment = Shipment.objects.get(pk=shipment_pk)
            except ObjectDoesNotExist:
                return False
            return self.check_permission_link(request, shipment)
        return request.user and request.user.is_authenticated

    def has_object_permission(self, request, view, obj):
        if self.check_has_owner_access(request, obj):
            return True

        if 'permission_link' not in request.query_params:
            return self.check_has_owner_access(request, obj)

        return self.check_permission_link(request, obj)

    def check_permission_link(self, request, shipment):
        permission_link = request.query_params.get('permission_link', None)
        if permission_link:
            try:
                permission_obj = PermissionLink.objects.get(pk=permission_link)
            except ObjectDoesNotExist:
                return False
            if not permission_obj.is_valid:
                return self.check_has_owner_access(request, shipment)
            return shipment.pk == permission_obj.shipment.pk and request.method == 'GET'

        return self.check_has_owner_access(request, shipment)

    def check_has_owner_access(self, request, obj):
        return request.user.is_authenticated and (has_owner_access(request, obj) or self.is_shipper(request, obj) or
                                                  self.is_carrier(request, obj) or self.is_moderator(request, obj))

    def is_carrier(self, request, shipment):
        """
        Custom permission for carrier documents management access
        """
        response = settings.REQUESTS_SESSION.get(f'{PROFILES_URL}/{shipment.carrier_wallet_id}/?is_active',
                                                 headers={'Authorization': f'JWT {get_jwt_from_request(request)}'})

        return response.status_code == status.HTTP_200_OK and request.method in ('GET', 'PATCH')

    def is_moderator(self, request, shipment):
        """
        Custom permission for moderator documents management access
        """
        if shipment.moderator_wallet_id:
            response = settings.REQUESTS_SESSION.get(f'{PROFILES_URL}/{shipment.moderator_wallet_id}/?is_active',
                                                     headers={'Authorization': f'JWT {get_jwt_from_request(request)}'})

        return (shipment.moderator_wallet_id and response.status_code == status.HTTP_200_OK and
                request.method in ('GET', 'PATCH'))

    def is_shipper(self, request, shipment):
        """
        Custom permission for shipper documents management access
        """
        response = settings.REQUESTS_SESSION.get(f'{PROFILES_URL}/{shipment.shipper_wallet_id}/?is_active',
                                                 headers={'Authorization': f'JWT {get_jwt_from_request(request)}'})

        return response.status_code == status.HTTP_200_OK and request.method in ('GET', 'PATCH')


class IsAuthenticatedOrDevice(permissions.IsAuthenticated):
    """
    Custom permission to allow users to access tracking data, or update if its a device
    """
    def has_permission(self, request, view):
        if request.method == 'POST':
            # Device authentication is handled during tracking data validation
            return True

        return super(IsAuthenticatedOrDevice, self).has_permission(request, view)
