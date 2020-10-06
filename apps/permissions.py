"""
Copyright 2019 ShipChain, Inc.

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""

import logging

from django.db.models import Q
from django.conf import settings

from rest_framework import permissions, status
from shipchain_common.authentication import get_jwt_from_request
from shipchain_common.utils import get_client_ip

from apps.shipments.models import Shipment

PROFILES_WALLET_URL = f'{settings.PROFILES_URL}/api/v1/wallet'

LOG = logging.getLogger('transmission')


def request_is_authenticated(request):
    return request.user.is_authenticated and settings.PROFILES_ENABLED


def get_user(request):
    if request_is_authenticated(request):
        return request.user.id, request.user.token.get('organization_id', None)
    return None, None


def shipment_owner_access_filter(request):
    user_id, organization_id = get_user(request)
    return Q(shipment__owner_id=organization_id) | Q(shipment__owner_id=user_id) if organization_id else \
        Q(shipment__owner_id=user_id)


def owner_access_filter(request):
    user_id, organization_id = get_user(request)
    return Q(owner_id=organization_id) | Q(owner_id=user_id) if organization_id else Q(owner_id=user_id)


def get_owner_id(request):
    user_id, organization_id = get_user(request)
    return organization_id if organization_id else user_id


def has_owner_access(request, obj):
    user_id, organization_id = get_user(request)
    return (organization_id and obj.owner_id == organization_id) or obj.owner_id == user_id


def get_organization_name(request):
    if request_is_authenticated(request):
        return request.user.token.get('organization_name', None)
    return None


def get_requester_username(request):
    if request_is_authenticated(request):
        return request.user.username
    return None


def shipment_exists(shipment_id):
    """
    Check whether a shipment_id included in a nested route exists.
    Returns False if it isn't otherwise returns the Shipment object
    """
    return Shipment.objects.filter(id=shipment_id).count()


class IsOwner(permissions.BasePermission):
    """
    Custom permission to only allow owners of an object to edit it
    """

    def has_object_permission(self, request, view, obj):
        # Permissions are only allowed to the owner of the shipment.
        return has_owner_access(request, obj)


class ShipmentExists(permissions.BasePermission):

    def has_permission(self, request, view):
        shipment_id = view.kwargs.get('shipment_pk') or view.kwargs.get('pk')

        if not shipment_exists(shipment_id):
            # The requested views are only accessible via nested routes
            requester = f'User [{request.user.id}]' if request.user.id else f'Ip [{get_client_ip(request)}]'
            LOG.warning(f'{requester}, is trying to access a non existing shipment: [{shipment_id}]')
            return False

        return True


class IsShipmentOwnerMixin:
    """
    Main shipment owner permission
    """

    @staticmethod
    def is_shipment_owner(request, shipment):
        return has_owner_access(request, shipment)


class IsShipperMixin:
    """
    Custom permission for Shipper shipment access
    """

    @staticmethod
    def has_shipper_permission(jwt, shipment):
        if not jwt:
            return False
        response = settings.REQUESTS_SESSION.get(f'{PROFILES_WALLET_URL}/{shipment.shipper_wallet_id}/?is_active',
                                                 headers={'Authorization': f'JWT {jwt}'})

        return response.status_code == status.HTTP_200_OK


class IsCarrierMixin:
    """
    Custom permission for Carrier shipment access
    """

    @staticmethod
    def has_carrier_permission(jwt, shipment):
        if not jwt:
            return False
        response = settings.REQUESTS_SESSION.get(f'{PROFILES_WALLET_URL}/{shipment.carrier_wallet_id}/?is_active',
                                                 headers={'Authorization': f'JWT {jwt}'})

        return response.status_code == status.HTTP_200_OK


class IsModeratorMixin:
    """
    Custom permission for Moderator shipment access
    """

    @staticmethod
    def has_moderator_permission(jwt, shipment):
        if jwt and shipment.moderator_wallet_id:
            response = settings.REQUESTS_SESSION.get(f'{PROFILES_WALLET_URL}/{shipment.moderator_wallet_id}/?is_active',
                                                     headers={'Authorization': f'JWT {jwt}'})

            return response.status_code == status.HTTP_200_OK
        return False


class IsNestedOwner(IsShipmentOwnerMixin, permissions.BasePermission):
    """
    Custom permission to only allow the owner access to a shipment object in a nested route
    """

    def has_permission(self, request, view):
        shipment = Shipment.objects.get(id=view.kwargs.get('shipment_pk'))

        return self.is_shipment_owner(request, shipment)


class IsNestedOwnerShipperCarrierModerator(IsShipmentOwnerMixin,
                                           IsCarrierMixin,
                                           IsModeratorMixin,
                                           IsShipperMixin,
                                           permissions.BasePermission):
    """
    Custom permission to only allow owner, shipper, moderator and carrier
    access to a shipment object on a nested route

    This class should be used in conjunction with ShipmentExists
    to validate the provided shipment_id in nested route

    Example:
        permission_classes = (IsAuthenticated, ShipmentExists, IsShipperCarrierModerator, )

        On a ConfigurableGenericViewSet:

        permission_classes = (IsAuthenticated, ShipmentExists, HasViewSetActionPermissions, IsShipperCarrierModerator, )

    The declaration order of these classes matters.

    """

    def has_permission(self, request, view):
        shipment = Shipment.objects.get(id=view.kwargs.get('shipment_pk'))
        jwt = get_jwt_from_request(request)

        return self.is_shipment_owner(request, shipment) or \
            self.has_shipper_permission(jwt, shipment) or \
            self.has_carrier_permission(jwt, shipment) or \
            self.has_moderator_permission(jwt, shipment)


class ORRequestResult:
    def __init__(self, op1_class, op2_class):
        self.op1_class = op1_class
        self.op2_class = op2_class

    def __call__(self, *args, **kwargs):
        op1 = self.op1_class(*args, **kwargs)
        op2 = self.op2_class(*args, **kwargs)
        return self.OR(op1, op2)

    class OR:
        def __init__(self, op1, op2):
            self.op1 = op1
            self.op2 = op2

        def has_permission(self, request, view):
            request.authorizing_permission_class = None
            if self.op1.has_permission(request, view):
                request.authorizing_permission_class = self.op1.__class__.__name__
            elif self.op2.has_permission(request, view):
                request.authorizing_permission_class = self.op2.__class__.__name__

            return request.authorizing_permission_class is not None

        def has_object_permission(self, request, view, obj):
            request.authorizing_object_permission_class = None
            if self.op1.has_object_permission(request, view, obj):
                request.authorizing_object_permission_class = self.op1.__class__.__name__
            elif self.op2.has_object_permission(request, view, obj):
                request.authorizing_object_permission_class = self.op2.__class__.__name__

            return request.authorizing_object_permission_class is not None
