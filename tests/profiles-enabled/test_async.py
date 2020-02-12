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
import datetime
import json

import pytest
from asgiref.sync import sync_to_async
from channels.layers import get_channel_layer
from channels.testing import WebsocketCommunicator
from django.db import models
from shipchain_common.test_utils import get_jwt
from asynctest import patch
from shipchain_common.utils import random_id

from apps.consumers import EventTypes, AppsConsumer
from apps.jobs.models import AsyncJob, MessageType
from apps.jobs.signals import job_update
from apps.routing import application
from apps.shipments.models import Shipment, Device, TrackingData, TelemetryData
from apps.shipments.signals import shipment_post_save, shipment_job_update

USER_ID = '00000000-0000-0000-0000-000000000009'


async def async_get_jwt(**kwargs):
    if 'sub' not in kwargs:
        kwargs['sub'] = USER_ID
    return await sync_to_async(get_jwt)(**kwargs)


async def get_communicator(my_jwt):
    return WebsocketCommunicator(application, f"ws/{USER_ID}/notifications",
                                 subprotocols=[f"base64.jwt.{my_jwt}", "base64.authentication.jwt"])


@pytest.fixture
async def communicator():
    communicator = await get_communicator(await async_get_jwt())
    connected, subprotocol = await communicator.connect()
    assert connected
    assert subprotocol == "base64.authentication.jwt"
    assert await communicator.receive_nothing()
    return communicator


@pytest.mark.asyncio
async def test_jwt_auth():
    # Expired JWT
    expired_jwt = await async_get_jwt(exp='1')
    communicator = await get_communicator(expired_jwt)
    connected, subprotocol = await communicator.connect()
    assert not connected
    assert subprotocol == 1000
    await communicator.disconnect()

    # User ID in token doesn't match route
    unauthorized_jwt = await async_get_jwt(sub='4686c616-fadf-4261-a2c2-6aaa504a1ae4')
    communicator = await get_communicator(unauthorized_jwt)
    connected, subprotocol = await communicator.connect()
    assert not connected
    assert subprotocol == 1000
    await communicator.disconnect()

    # Invalid protocols
    valid_jwt = await async_get_jwt()
    communicator = WebsocketCommunicator(application, f"ws/{USER_ID}/notifications",
                                         subprotocols=[f"base64.wat.{valid_jwt}", "base64.authentication.wat"])
    connected, subprotocol = await communicator.connect()
    assert not connected
    assert subprotocol == 1000
    await communicator.disconnect()


@pytest.mark.asyncio
async def test_jwt_refresh():
    # It's difficult to test JWT expiration w/ channels/asyncio - so we have to test using the mocked consumer
    # Setup an AppsConsumer with no authenticated user in the scope
    consumer = AppsConsumer(scope={'subprotocols': [], 'url_route': {'kwargs': {'user_id': USER_ID}}})

    # Mock consumer.send and consumer.close
    with patch("channels.generic.websocket.AsyncWebsocketConsumer.send") as fake_send:
        with patch("channels.generic.websocket.AsyncWebsocketConsumer.close") as fake_close:
            # Test that invalid/missing/expired auth results in socket close
            await consumer.receive(json.dumps({"hello": "world"}))
            assert not fake_send.called
            assert fake_close.called
            fake_send.reset_mock()
            fake_close.reset_mock()

            # Ensure refresh_jwt message gets accepted even without valid auth
            await consumer.receive(json.dumps({"event": "refresh_jwt", "data": await async_get_jwt()}))
            assert not fake_send.called
            assert not fake_close.called

            # After refreshing token, socket should be open/active
            await consumer.receive(json.dumps({"hello": "world"}))
            assert fake_send.called
            assert not fake_close.called


@pytest.mark.asyncio
@pytest.mark.django_db
async def test_job_notification(communicator):
    class DummyRPCClient:
        def do_whatever(self):
            pass

    # Disable Shipment post-save signal
    await sync_to_async(models.signals.post_save.disconnect)(sender=Shipment, dispatch_uid='shipment_post_save')

    shipment, _ = await sync_to_async(Shipment.objects.get_or_create)(
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

    job = await sync_to_async(AsyncJob.rpc_job_for_listener)(rpc_method=DummyRPCClient.do_whatever, rpc_parameters=[],
                                                             signing_wallet_id='FAKE_WALLET_ID', shipment=shipment)

    # Disable Shipment job update signal
    await sync_to_async(job_update.disconnect)(shipment_job_update, sender=Shipment, dispatch_uid='shipment_job_update')

    await sync_to_async(job.message_set.create)(type=MessageType.ETH_TRANSACTION, body=json.dumps({'foo': 'bar'}))

    # Enable Shipment job update signal
    await sync_to_async(job_update.connect)(shipment_job_update, sender=Shipment, dispatch_uid='shipment_job_update')

    response = await communicator.receive_json_from()
    assert response['event'] == EventTypes.asyncjob_update.name
    assert response['data']['data']['id'] == job.id

    await communicator.disconnect()


@pytest.mark.asyncio
@pytest.mark.django_db
async def test_trackingdata_notification(communicator):
    # Disable Shipment post-save signal
    await sync_to_async(models.signals.post_save.disconnect)(sender=Shipment, dispatch_uid='shipment_post_save')

    shipment, _ = await sync_to_async(Shipment.objects.get_or_create)(
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

    device = await sync_to_async(Device.objects.create)(id=random_id())

    tracking_data = await sync_to_async(TrackingData.objects.create)(
        id='FAKE_TRACKING_DATA_ID',
        device=device,
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

    assert response['event'] == EventTypes.trackingdata_update.name
    assert response['data']['shipment_id'] == shipment.id
    assert response['data']['feature']['type'] == 'Feature'
    assert response['data']['feature']['geometry']['coordinates'][0] == tracking_data.longitude

    t_data = await sync_to_async(TrackingData.objects.get)(id='FAKE_TRACKING_DATA_ID')
    await sync_to_async(t_data.delete)()

    await communicator.disconnect()


@pytest.mark.asyncio
async def test_telemetrydata_notification(communicator):
    # Disable Shipment post-save signal
    await sync_to_async(models.signals.post_save.disconnect)(sender=Shipment, dispatch_uid='shipment_post_save')

    shipment, _ = await sync_to_async(Shipment.objects.get_or_create)(
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

    device = await sync_to_async(Device.objects.create)(id=random_id())

    telemetry_id = random_id()
    telemetry_data = await sync_to_async(TelemetryData.objects.create)(
        id=telemetry_id,
        device=device,
        shipment=shipment,
        hardware_id='hardware_id',
        sensor_id='sensor_id',
        value=867.5309,
        version='1.1.0',
        timestamp=datetime.datetime.now(tz=None)
    )

    response = await communicator.receive_json_from()

    assert response['event'] == EventTypes.trackingdata_update.name
    assert response['data']['shipment_id'] == shipment.id
    assert response['data']['feature']['value'] == telemetry_data.value

    t_data = await sync_to_async(TelemetryData.objects.get)(id=telemetry_id)
    await sync_to_async(t_data.delete)()

    await communicator.disconnect()


@pytest.mark.asyncio
@pytest.mark.django_db
async def test_shipmentupdate_notification(communicator):
    # Disable Shipment post-save signal
    await sync_to_async(models.signals.post_save.disconnect)(sender=Shipment, dispatch_uid='shipment_post_save')

    shipment, _ = await sync_to_async(Shipment.objects.get_or_create)(
        id=random_id(),
        owner_id=USER_ID,
        storage_credentials_id=random_id(),
        shipper_wallet_id=random_id(),
        carrier_wallet_id=random_id(),
        contract_version='1.0.0'
    )

    # Update shipment (should get a message)
    shipment.carriers_scac = 'TESTING123'
    await sync_to_async(shipment.save)()
    # Have to manually send message to channel

    channel_layer = get_channel_layer()
    await channel_layer.group_send(shipment.owner_id, {
        "type": "shipments.update",
        "shipment_id": shipment.id
    })

    # Re-enable Shipment post-save signal
    await sync_to_async(models.signals.post_save.connect)(shipment_post_save, sender=Shipment,
                                                          dispatch_uid='shipment_post_save')
    response = await communicator.receive_json_from()

    assert response['event'] == EventTypes.shipment_update.name
    assert response['data']['data']['type'] == 'Shipment'
    assert response['data']['data']['attributes']['carriers_scac'] == shipment.carriers_scac

    await communicator.disconnect()
