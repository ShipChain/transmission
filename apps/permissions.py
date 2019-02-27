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
from django.db.models import Q
from rest_framework import permissions


def get_user(request):
    if request.user.is_authenticated:
        return request.user.id, request.user.token.get('organization_id', None)
    return None, None


def owner_access_filter(request):
    user_id, organization_id = get_user(request)
    return Q(owner_id=organization_id) | Q(owner_id=user_id) if organization_id else Q(owner_id=user_id)


def get_owner_id(request):
    user_id, organization_id = get_user(request)
    return organization_id if organization_id else user_id


def has_owner_access(request, obj):
    user_id, organization_id = get_user(request)
    return (organization_id and obj.owner_id == organization_id) or obj.owner_id == user_id


class IsOwner(permissions.BasePermission):
    """
    Custom permission to only allow owners of an object to edit it
    """
    def has_object_permission(self, request, view, obj):
        # Permissions are only allowed to the owner of the shipment.
        return has_owner_access(request, obj)
