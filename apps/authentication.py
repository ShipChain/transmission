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
from collections import namedtuple
from django.conf import settings
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from rest_framework import exceptions
from rest_framework.permissions import BasePermission
from rest_framework_jwt.settings import api_settings
from rest_framework_jwt.authentication import JSONWebTokenAuthentication, jwt_decode_handler

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


def passive_credentials_authentication(payload):
    if 'sub' not in payload:
        raise exceptions.AuthenticationFailed('Invalid payload.')

    payload['pk'] = payload['sub']
    payload = namedtuple("User", payload.keys())(*payload.values())
    payload = api_settings.JWT_PAYLOAD_HANDLER(payload)

    user = AuthenticatedUser(payload)

    return user


class PassiveJSONWebTokenAuthentication(JSONWebTokenAuthentication):
    def authenticate_credentials(self, payload):
        return passive_credentials_authentication(payload)


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
                payload = await sync.sync_to_async(jwt_decode_handler)(self.scope['jwt'])
                user = await sync.sync_to_async(passive_credentials_authentication)(payload)
        except Exception:
            pass

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
