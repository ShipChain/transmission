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
import warnings
import uuid
import datetime
from collections import namedtuple
import jwt
from jwt.exceptions import InvalidTokenError

from asgiref import sync
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.conf import settings
from django.contrib.auth import get_user_model
from rest_framework import exceptions
from rest_framework.exceptions import APIException
from rest_framework.permissions import BasePermission
from rest_framework_simplejwt.authentication import JWTAuthentication

from settings import SIMPLE_JWT
from .utils import parse_dn


def get_username_field():
    try:
        username_field = get_user_model().USERNAME_FIELD
    except AttributeError:
        username_field = 'username'

    return username_field


def get_username(user):
    try:
        username = user.get_username()
    except AttributeError:
        username = user.username

    return username


def jwt_decode_handler(token):
    options = {
        'verify_exp': True,
    }
    # get user from token, BEFORE verification, to get user secret key
    return jwt.decode(
        token,
        SIMPLE_JWT['VERIFYING_KEY'],
        True,
        options=options,
        leeway=0,
        audience=SIMPLE_JWT['AUDIENCE'],
        issuer=None,
        algorithms=[SIMPLE_JWT['ALGORITHM']]
    )


def jwt_payload_handler(user):
    username_field = get_username_field()
    username = get_username(user)

    warnings.warn(
        'The following fields will be removed in the future: '
        '`email` and `user_id`. ',
        DeprecationWarning
    )

    payload = {
        'user_id': user.pk,
        'username': username,
        'exp': datetime.datetime.utcnow() + datetime.timedelta(seconds=300)
    }
    if hasattr(user, 'email'):
        payload['email'] = user.email
    if isinstance(user.pk, uuid.UUID):
        payload['user_id'] = str(user.pk)

    payload[username_field] = username
    payload['aud'] = SIMPLE_JWT['AUDIENCE']

    return payload


def get_token_from_tokenuser(request):
    """
    This is for retreiving the decoded JWT from the simplejwt token user request.
    """
    return (request.authenticators[-1].get_raw_token(request.authenticators[-1].get_header(request)).decode()
            if request.authenticators else None)


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


def passive_credentials_auth(payload):
    if 'sub' not in payload:
        raise exceptions.AuthenticationFailed('Invalid payload.')

    payload['pk'] = payload['sub']
    payload = namedtuple("User", payload.keys())(*payload.values())
    print(payload)
    payload = jwt_payload_handler(payload)

    user = AuthenticatedUser(payload)

    return user


def get_token_from_tokenuser(request):
    """
    This is for retreiving the decoded JWT from the simplejwt token user request.
    """
    return (request.authenticators[-1].get_raw_token(request.authenticators[-1].get_header(request)).decode()
            if request.authenticators else None)


class PassiveJSONWebTokenAuthentication(JWTAuthentication):
    def authenticate_credentials(self, payload):
        return passive_credentials_auth(payload)


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
        jwt_from_protocols = None

        # Initially parse jwt out of subprotocols
        for protocol in self.scope['subprotocols']:
            if protocol.startswith('base64.jwt.'):
                jwt_from_protocols = protocol.split('base64.jwt.')[1]

        return jwt_from_protocols

    async def _get_user(self):
        user = None

        try:
            if self.scope['jwt']:
                payload = await sync.sync_to_async(jwt_decode_handler)(self.scope['jwt'])
                user = await sync.sync_to_async(passive_credentials_auth)(payload)
        except (APIException, InvalidTokenError):
            # Can ignore JWT auth failures, scope['user'] will not be set.
            pass

        return user


class EngineRequest(BasePermission):
    def has_permission(self, request, view):
        if settings.ENVIRONMENT in ('LOCAL',):
            return True
        if ('X_NGINX_SOURCE' in request.META and request.META['X_NGINX_SOURCE'] == 'internal'
                and request.META['X_SSL_CLIENT_VERIFY'] == 'SUCCESS'):
            certificate_cn = parse_dn(request.META['X_SSL_CLIENT_DN'])['CN']
            return certificate_cn == f'engine.{settings.ENVIRONMENT.lower()}-internal'
        return False
