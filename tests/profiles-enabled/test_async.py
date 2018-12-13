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
import json
import datetime

import jwt
import pytest
from asgiref.sync import sync_to_async
from channels.testing import WebsocketCommunicator
from django.conf import settings
from django.db import models
from django_mock_queries.mocks import mocked_relations
from mock import patch

from apps.jobs.models import AsyncJob, JobListener, MessageType
from apps.shipments.models import Shipment, Device, TrackingData

from apps.shipments.signals import shipment_post_save
from apps.consumers import EventTypes
from apps.routing import application

USER_ID = '00000000-0000-0000-0000-000000000000'


async def get_jwt(exp=None, sub=USER_ID):
    payload = {'email': 'fake@shipchain.io', 'username': 'fake@shipchain.io', 'sub': sub,
                        'aud': settings.JWT_AUTH['JWT_AUDIENCE']}
    if exp:
        payload['exp'] = exp

    return jwt.encode(payload=payload, key=settings.JWT_AUTH['JWT_PRIVATE_KEY'],
                      algorithm='RS256',
                      headers={'kid': '230498151c214b788dd97f22b85410a5'}).decode()


async def get_communicator(my_jwt):
    return WebsocketCommunicator(application, f"ws/{USER_ID}/notifications",
                                 subprotocols=[f"base64.jwt.{my_jwt}", "base64.authentication.jwt"])


@pytest.fixture
async def communicator():
    communicator = await get_communicator(await get_jwt())
    connected, subprotocol = await communicator.connect()
    assert connected
    assert subprotocol == "base64.authentication.jwt"
    assert await communicator.receive_nothing()
    return communicator


@pytest.mark.asyncio
async def test_jwt_auth():
    # Expired JWT
    expired_jwt = await get_jwt(exp='1')
    communicator = await get_communicator(expired_jwt)
    connected, subprotocol = await communicator.connect()
    assert not connected
    assert subprotocol == 1000
    await communicator.disconnect()

    # User ID in token doesn't match route
    unauthorized_jwt = await get_jwt(sub='4686c616-fadf-4261-a2c2-6aaa504a1ae4')
    communicator = await get_communicator(unauthorized_jwt)
    connected, subprotocol = await communicator.connect()
    assert not connected
    assert subprotocol == 1000
    await communicator.disconnect()

    # Invalid protocols
    valid_jwt = await get_jwt()
    communicator = WebsocketCommunicator(application, f"ws/{USER_ID}/notifications",
                                         subprotocols=[f"base64.wat.{valid_jwt}", "base64.authentication.wat"])
    connected, subprotocol = await communicator.connect()
    assert not connected
    assert subprotocol == 1000
    await communicator.disconnect()


@pytest.mark.asyncio
async def test_jwt_refresh():
    my_jwt = await get_jwt()
    communicator = await get_communicator(my_jwt)

    expired_jwt = await get_jwt(exp='1')
    await communicator.send_to(text_data=json.dumps({"event": "refresh_jwt", "data": expired_jwt}))

    await communicator.send_to(json.dumps({"hello": "world"}))
    await communicator.receive_nothing()  # Socket should be closed due to expired jwt
    await communicator.disconnect()

    # TODO: Try to find a way to get freezegun to work with django channels to properly test token expiration

    communicator = await get_communicator(my_jwt)
    await communicator.send_json_to({"event": "refresh_jwt", "data": my_jwt})
    await communicator.send_json_to({"hello": "world"})
    response = await communicator.receive_json_from()
    assert response['event'] == EventTypes.error.name
    assert response['data'] == "This websocket endpoint is read-only"

    await communicator.disconnect()


@pytest.mark.asyncio
@pytest.mark.django_db
async def test_job_notification(communicator):
    class DummyRPCClient:
        def do_whatever(self):
            pass

    class DummyListener(models.Model):
        id = models.CharField(primary_key=True, max_length=36)
        owner_id = models.CharField(null=False, max_length=36)

        class Meta:
            app_label = 'apps.jobs'

    listener = DummyListener(id='FAKE_LISTENER_ID', owner_id=USER_ID)

    with mocked_relations(JobListener):
        job = await sync_to_async(AsyncJob.rpc_job_for_listener)(rpc_method=DummyRPCClient.do_whatever, rpc_parameters=[],
                                                                 signing_wallet_id='FAKE_WALLET_ID', listener=listener)
        from django_mock_queries.query import MockSet, Mock
        from django_mock_queries.mocks import MockOneToManyMap

        with patch.object(AsyncJob, 'joblistener_set', MockOneToManyMap(AsyncJob.joblistener_set)):
            job.joblistener_set = MockSet(Mock(listener=listener))

            await sync_to_async(job.message_set.create)(type=MessageType.ETH_TRANSACTION, body=json.dumps({'foo': 'bar'}))
            assert job.joblistener_set.count() == 1
            response = await communicator.receive_json_from()
            assert response['event'] == EventTypes.asyncjob_update.name
            assert response['data']['id'] == job.id

    await communicator.disconnect()


@pytest.mark.asyncio
@pytest.mark.django_db
async def test_trackingdata_notification(communicator):

    # Disable Shipment post-save signal
    await sync_to_async(models.signals.post_save.disconnect)(sender=Shipment, dispatch_uid='shipment_post_save')

    shipment = await sync_to_async(Shipment.objects.create)(
        id='FAKE_SHIPMENT_ID',
        owner_id=USER_ID,
        storage_credentials_id='FAKE_STORAGE_CREDENTIALS_ID',
        shipper_wallet_id='FAKE_SHIPPER_WALLET_ID',
        carrier_wallet_id='FAKE_CARRIER_WALLET_ID',
        contract_version='1.0.0'
    )

    # Re-enable Shipment post-save signal
    await sync_to_async(models.signals.post_save.connect)(shipment_post_save, sender=Shipment,
                                                          dispatch_uid='shipment_post_save')

    device = await sync_to_async(Device.objects.create)(id='FAKE_DEVICE_ID')

    tracking_data = await sync_to_async(TrackingData.objects.create)(
        id='FAKE_TRACKING_DATA_ID',
        device_id=device,
        shipment=shipment,
        latitude=75.65,
        longitude=84.36,
        altitude=36.65,
        source='gps',
        uncertainty=66,
        speed=36,
        version='1.1.0',
        timestamp=datetime.datetime.now(tz=None)
    )

    response = await communicator.receive_json_from()

    assert response['event'] == EventTypes.new_tracking_data.name
    assert response['data']['type'] == 'Feature'
    assert response['data']['geometry']['coordinates'][0] == tracking_data.longitude

    t_data = await sync_to_async(TrackingData.objects.get)(id='FAKE_TRACKING_DATA_ID')
    await sync_to_async(t_data.delete)()

    await communicator.disconnect()
