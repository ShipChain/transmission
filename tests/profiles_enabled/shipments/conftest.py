#  Copyright 2020 ShipChain, Inc.
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.
import json
import random
from datetime import datetime

import pytest
import re
from django.conf import settings
from rest_framework import status
from shipchain_common.test_utils import AssertionHelper
from shipchain_common.utils import random_id

from apps.routes.models import Route
from apps.shipments.models import Shipment, Device, PermissionLink

NUM_DEVICES = 7
BBOX = [-90.90, 30.90, -78.80, 36.80]
NUM_TRACKING_DATA_BBOX = 3



def create_organization_shipments(user, profiles_ids):
    return [Shipment.objects.create(vault_id=random_id(),
                                    owner_id=user.token.payload['organization_id'],
                                    **profiles_ids
                                    ) for i in range(0, 3)]


@pytest.fixture
def tracking_data():
    return {
        'position': {
            'latitude': 75.0587610,
            'longitude': -35.628643,
            'altitude': 554,
            'source': 'Gps',
            'uncertainty': 92,
            'speed': 34.56
        },
        'version': '1.0.0',
        'timestamp': datetime.utcnow().isoformat()
    }

@pytest.fixture
def devices():
    list_device = []
    for i in range(0, NUM_DEVICES):
        list_device.append(Device.objects.create(id=random_id()))

    return list_device

@pytest.fixture
def overview_tracking_data():
    in_bbox, out_of_bbox = [], []
    for i in range(0, NUM_TRACKING_DATA_BBOX):
        in_bbox.append(
            {
                'latitude': random.uniform(BBOX[1], BBOX[3]),
                'longitude': random.uniform(BBOX[0], BBOX[2]),
                'source': 'GPS',
                'timestamp': datetime.utcnow(),
                'version': '1.1.0'
            }
        )

        out_of_bbox.append(
            {
                'latitude': random.uniform(BBOX[1], BBOX[3]),
                'longitude': random.uniform(BBOX[1], BBOX[3]),
                'source': 'GPS',
                'timestamp': datetime.utcnow(),
                'version': '1.1.0'
            }
        )

    return in_bbox, out_of_bbox

@pytest.fixture
def alice_organization_shipments(user_alice, mocked_engine_rpc, mocked_iot_api, profiles_ids):
    return create_organization_shipments(user_alice, profiles_ids)


@pytest.fixture
def alice_organization_shipment_fixtures(alice_organization_shipments, profiles_ids):
    return [AssertionHelper.EntityRef(
        resource='Shipment',
        pk=shipment.id,
        attributes={
            'vault_id': shipment.vault_id,
            'owner_id': shipment.owner_id,
            **profiles_ids
        },
    ) for shipment in alice_organization_shipments]


@pytest.fixture
def bob_organization_shipments(user_bob, mocked_engine_rpc, mocked_iot_api, profiles_ids):
    return create_organization_shipments(user_bob, profiles_ids)


@pytest.fixture
def bob_organization_shipment_fixtures(bob_organization_shipments, profiles_ids):
    return [AssertionHelper.EntityRef(
        resource='Shipment',
        pk=shipment.id,
        attributes={
            'vault_id': shipment.vault_id,
            'owner_id': shipment.owner_id,
            **profiles_ids
        },
    ) for shipment in bob_organization_shipments]


@pytest.fixture
def mock_device_retrieval(mock_successful_wallet_owner_calls, device, device_two):
    mock_successful_wallet_owner_calls.register_uri(
        mock_successful_wallet_owner_calls.GET,
        f'{settings.PROFILES_URL}/api/v1/device/{device.id}/?is_active',
        status=status.HTTP_200_OK
    )
    mock_successful_wallet_owner_calls.register_uri(
        mock_successful_wallet_owner_calls.GET,
        f'{settings.PROFILES_URL}/api/v1/device/{device_two.id}/?is_active',
        status=status.HTTP_200_OK
    )
    return mock_successful_wallet_owner_calls


@pytest.fixture
def mock_device_retrieval_fails(mock_successful_wallet_owner_calls, device, device_two):
    mock_successful_wallet_owner_calls.register_uri(
        mock_successful_wallet_owner_calls.GET,
        f'{settings.PROFILES_URL}/api/v1/device/{device.id}/?is_active',
        status=status.HTTP_404_NOT_FOUND
    )
    mock_successful_wallet_owner_calls.register_uri(
        mock_successful_wallet_owner_calls.GET,
        f'{settings.PROFILES_URL}/api/v1/device/{device_two.id}/?is_active',
        status=status.HTTP_404_NOT_FOUND
    )
    return mock_successful_wallet_owner_calls


@pytest.fixture
def route_with_device_alice(org_id_alice, device):
    return Route.objects.create(owner_id=org_id_alice, device=device)


@pytest.fixture
def permission_link_shipment_alice(shipment_alice):
    return PermissionLink.objects.create(shipment=shipment_alice, name="Alice Permission Link")
