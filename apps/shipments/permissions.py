from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from rest_framework import permissions, status

from apps.authentication import get_jwt_from_request
from apps.permissions import has_owner_access
from .models import PermissionLink, Shipment


PROFILES_URL = f'{settings.PROFILES_URL}/api/v1/wallet'


class IsShipmentOwner(permissions.BasePermission):
    """
    Custom permission to allow only the owner or a wallet owner to interact with a shipment's permission link
    """

    def has_object_permission(self, request, view, obj):
        shipment_id = view.kwargs.get('shipment_pk', None)
        if shipment_id:
            shipment = shipment_exists(shipment_id)
            if not shipment:
                return False
            return check_has_shipment_owner_access(request, shipment)
        return False

    def has_permission(self, request, view):
        shipment_id = view.kwargs.get('shipment_pk', None)
        if shipment_id:
            shipment = shipment_exists(shipment_id)
            if not shipment:
                return False
            return check_has_shipment_owner_access(request, shipment)
        return False


class IsListenerOwner(permissions.BasePermission):
    """
    Custom permission to only allow owners of an object to edit it
    """

    def has_permission(self, request, view):
        shipment_id = view.kwargs.get('shipment_pk', None)

        if shipment_id:
            shipment = shipment_exists(shipment_id)
            if not shipment:
                return False
            return check_permission_link(request, shipment)

        # Transactions are still accessible on their own endpoint
        return request.user.is_authenticated

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
        shipment_pk = view.kwargs.get('pk', None) or view.kwargs.get('shipment_pk', None)

        # The shipments can only be accessible via permission links only on shipment-detail endpoints
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
            shipment = shipment_exists(shipment_pk)
            if not shipment:
                return False
            return check_permission_link(request, shipment)
        return request.user and request.user.is_authenticated

    def has_object_permission(self, request, view, obj):
        if check_has_shipment_owner_access(request, obj):
            return True

        if 'permission_link' not in request.query_params:
            return check_has_shipment_owner_access(request, obj)

        return check_permission_link(request, obj)


class IsAuthenticatedOrDevice(permissions.IsAuthenticated):
    """
    Custom permission to allow users to access tracking data, or update if its a device
    """
    def has_permission(self, request, view):
        if request.method == 'POST':
            # Device authentication is handled during tracking data validation
            return True

        return super(IsAuthenticatedOrDevice, self).has_permission(request, view)


def is_carrier(request, shipment):
    """
    Custom permission for carrier shipment access
    """
    response = settings.REQUESTS_SESSION.get(f'{PROFILES_URL}/{shipment.carrier_wallet_id}/?is_active',
                                             headers={'Authorization': f'JWT {get_jwt_from_request(request)}'})

    return response.status_code == status.HTTP_200_OK and request.method in ('GET', 'PATCH')


def is_moderator(request, shipment):
    """
    Custom permission for moderator shipment access
    """
    if shipment.moderator_wallet_id:
        response = settings.REQUESTS_SESSION.get(f'{PROFILES_URL}/{shipment.moderator_wallet_id}/?is_active',
                                                 headers={'Authorization': f'JWT {get_jwt_from_request(request)}'})

        return response.status_code == status.HTTP_200_OK and request.method in ('GET', 'PATCH')

    return False


def is_shipper(request, shipment):
    """
    Custom permission for shipper shipment access
    """
    response = settings.REQUESTS_SESSION.get(f'{PROFILES_URL}/{shipment.shipper_wallet_id}/?is_active',
                                             headers={'Authorization': f'JWT {get_jwt_from_request(request)}'})

    return response.status_code == status.HTTP_200_OK and request.method in ('GET', 'PATCH')


def shipment_exists(shipment_id):
    """
    Check whether a shipment_id included in a nested route exists.
    Returns False if it isn't otherwise returns the Shipment object
    """
    try:
        shipment_obj = Shipment.objects.get(pk=shipment_id)
    except ObjectDoesNotExist:
        return False

    return shipment_obj


def check_permission_link(request, shipment_obj):
    permission_link_id = request.query_params.get('permission_link', None)
    if permission_link_id:
        try:
            permission_obj = PermissionLink.objects.get(pk=permission_link_id)
        except ObjectDoesNotExist:
            return False
        if not permission_obj.is_valid:
            return check_has_shipment_owner_access(request, shipment_obj)

        return shipment_obj.pk == permission_obj.shipment.pk and request.method == 'GET'

    return check_has_shipment_owner_access(request, shipment_obj)


def check_has_shipment_owner_access(request, obj):
    return request.user.is_authenticated and (has_owner_access(request, obj) or is_shipper(request, obj) or
                                              is_carrier(request, obj) or is_moderator(request, obj))
