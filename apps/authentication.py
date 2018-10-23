"""
Copyright 2018 ShipChain, Inc.

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

from collections import namedtuple
from django.conf import settings
from rest_framework import exceptions
from rest_framework.permissions import BasePermission
from rest_framework_jwt.settings import api_settings
from rest_framework_jwt.authentication import JSONWebTokenAuthentication

from .utils import parse_dn


class AuthenticatedUser:
    def __init__(self, payload):
        self.id = payload.get('user_id')  # pylint:disable=invalid-name
        self.username = payload.get('username')
        self.email = payload.get('email')

    def is_authenticated(self):
        return True

    def is_staff(self):
        return False

    def is_superuser(self):
        return False


class PassiveJSONWebTokenAuthentication(JSONWebTokenAuthentication):
    def authenticate_credentials(self, payload):
        if 'sub' not in payload:
            raise exceptions.AuthenticationFailed('Invalid payload.')

        payload['pk'] = payload['sub']
        payload = namedtuple("User", payload.keys())(*payload.values())
        payload = api_settings.JWT_PAYLOAD_HANDLER(payload)

        user = AuthenticatedUser(payload)

        return user


class EngineRequest(BasePermission):
    def has_permission(self, request, view):
        if settings.ENVIRONMENT in ('LOCAL',):
            return True
        elif ('X_NGINX_SOURCE' in request.META and request.META['X_NGINX_SOURCE'] == 'internal'
              and request.META['X_SSL_CLIENT_VERIFY'] == 'SUCCESS'):
            certificate_cn = parse_dn(request.META['X_SSL_CLIENT_DN'])['CN']
            return certificate_cn == f'engine.{settings.ENVIRONMENT.lower()}-internal'
        return False
