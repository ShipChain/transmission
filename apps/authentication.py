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
from django.core.cache import cache

from rest_framework.exceptions import APIException
from rest_framework_simplejwt.tokens import TokenError
from shipchain_common.authentication import InternalRequest, passive_credentials_auth, PermissionedTokenUser

from apps.shipments.models import AccessRequest


class AsyncJsonAuthConsumer(AsyncJsonWebsocketConsumer):
    """
    Consumer that requires user to be present in the scope.
    """
    async def connect(self):
        if await self._authenticate():
            await self.channel_layer.group_add(self.scope['user'].id, self.channel_name)
            organization_id = await sync.sync_to_async(self.scope['user'].token.get)('organization_id', None)
            if organization_id:
                await self.channel_layer.group_add(organization_id, self.channel_name)
            await self.accept('base64.authentication.jwt')

    async def disconnect(self, code):
        if self.scope['user']:
            await self.channel_layer.group_discard(self.scope['user'].id, self.channel_name)
            organization_id = await sync.sync_to_async(self.scope['user'].token.get)('organization_id', None)
            if organization_id:
                await self.channel_layer.group_discard(organization_id, self.channel_name)
        await super().disconnect(code)

    async def receive(self, text_data=None, bytes_data=None, **kwargs):
        if text_data:
            json = await self.decode_json(text_data)
            # Handle jwt_refresh requests before attempting authentication
            refresh_request = 'event' in json and 'data' in json and json['event'] == 'refresh_jwt'
            if refresh_request:
                self.scope['jwt'] = json['data']
            if await self._authenticate() and not refresh_request:
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
        except (APIException, TokenError):
            # Can ignore JWT auth failures, scope['user'] will not be set.
            pass

        return user


class DocsLambdaRequest(InternalRequest):
    SERVICE_NAME = 'document-management-s3-hook'


class TransmissionTokenUser(PermissionedTokenUser):
    @property
    def access_request_shipments(self):
        cache_key = f'access_request_shipments_{self.id}'
        shipment_ids = cache.get(cache_key)

        if not shipment_ids:
            shipment_ids = AccessRequest.objects.filter(
                requester_id=self.id, approved=True
            ).values_list('shipment_id', flat=True)

            cache.set(cache_key, shipment_ids)

        return shipment_ids
