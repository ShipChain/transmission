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
from asgiref import sync
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.conf import settings
from jwt.exceptions import InvalidTokenError
from rest_framework.exceptions import APIException, AuthenticationFailed
from rest_framework.permissions import BasePermission
from rest_framework_simplejwt.authentication import JWTTokenUserAuthentication

from .utils import parse_dn

PASSIVE_JWT_AUTHENTICATION = JWTTokenUserAuthentication()


def passive_credentials_auth(jwt):
    if jwt == "":
        raise AuthenticationFailed('No JWT provided with request')
    return PASSIVE_JWT_AUTHENTICATION.get_user(PASSIVE_JWT_AUTHENTICATION.get_validated_token(jwt))


def get_jwt_from_request(request):
    """
    This is for retrieving the decoded JWT from the a request via the simplejwt authenticator.
    """
    if not settings.PROFILES_ENABLED:
        return None
    return (request.authenticators[-1].get_raw_token(request.authenticators[-1].get_header(request)).decode()
            if request.authenticators else None)


class AsyncJsonAuthConsumer(AsyncJsonWebsocketConsumer):
    """
    Consumer that requires user to be present in the scope.
    """
    async def connect(self):
        if await self._authenticate():
            await self.channel_layer.group_add(self.scope['user'].id, self.channel_name)
            await self.accept('base64.authentication.jwt')

    async def disconnect(self, code):
        if self.scope['user']:
            await self.channel_layer.group_discard(self.scope['user'].id, self.channel_name)
        await super().disconnect(code)

    async def receive(self, text_data=None, bytes_data=None, **kwargs):
        if await self._authenticate():
            if text_data:
                json = await self.decode_json(text_data)
                if 'event' in json and 'data' in json and json['event'] == 'refresh_jwt':
                    self.scope['jwt'] = json['data']
                else:
                    await self.receive_json(json, **kwargs)
            else:
                raise ValueError("No text section for incoming WebSocket frame!")

    async def send(self, text_data=None, bytes_data=None, close=False):
        if await self._authenticate():
            await super().send(text_data, bytes_data, close)

    async def _authenticate(self):
        if "jwt" not in self.scope:
            self.scope["jwt"] = await self._get_jwt_from_subprotocols()
        self.scope["user"] = await self._get_user()
        if not self.scope['user'] or ('user_id' in self.scope['url_route']['kwargs'] and
                                      self.scope['url_route']['kwargs']['user_id'] != self.scope['user'].id):
            await self.close()
            return False
        return True

    async def _get_jwt_from_subprotocols(self):
        jwt = None

        # Initially parse jwt out of subprotocols
        for protocol in self.scope['subprotocols']:
            if protocol.startswith('base64.jwt.'):
                jwt = protocol.split('base64.jwt.')[1]

        return jwt

    async def _get_user(self):
        user = None

        try:
            if self.scope['jwt']:
                user = await sync.sync_to_async(passive_credentials_auth)(self.scope['jwt'])
        except (APIException, InvalidTokenError):
            # Can ignore JWT auth failures, scope['user'] will not be set.
            pass

        return user


def is_internal_call(request):
    return ('X_NGINX_SOURCE' in request.META and request.META['X_NGINX_SOURCE'] == 'internal'
            and request.META['X_SSL_CLIENT_VERIFY'] == 'SUCCESS')


class InternalRequest(BasePermission):
    def has_permission(self, request, view):
        if settings.ENVIRONMENT in ('LOCAL', 'INT'):
            return True
        if is_internal_call(request):
            certificate_cn = parse_dn(request.META['X_SSL_CLIENT_DN'])['CN']
            return certificate_cn == f'{self.SERVICE_NAME}.{settings.ENVIRONMENT.lower()}-internal'
        return False


class EngineRequest(InternalRequest):
    SERVICE_NAME = 'engine'


class DocsLambdaRequest(InternalRequest):
    SERVICE_NAME = 'document-management-s3-hook'
