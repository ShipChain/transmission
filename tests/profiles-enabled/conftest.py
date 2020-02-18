#  Copyright 2019 ShipChain, Inc.
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
import pytest

from django.conf import settings as test_settings

from rest_framework import status
from rest_framework.request import ForcedAuthentication
from rest_framework.test import APIClient
from shipchain_common.utils import random_id
from shipchain_common.test_utils import get_jwt

from apps.authentication import passive_credentials_auth
from apps.shipments.models import Shipment


def fake_get_raw_token(self, header):
    return header.split()[1]


def fake_get_header(self, request):
    return b'JWT dummy'


ForcedAuthentication.get_raw_token = fake_get_raw_token
ForcedAuthentication.get_header = fake_get_header

USER_ID = random_id()
USER_2_ID = random_id()
SHIPPER_ID = random_id()
ORGANIZATION_ID = random_id()
ORGANIZATION_2_ID = random_id()
VAULT_ID = random_id()


@pytest.fixture(scope='session')
def token():
    return get_jwt(username='user1@shipchain.io', sub=USER_ID, organization_id=ORGANIZATION_ID)


@pytest.fixture(scope='session')
def user(token):
    return passive_credentials_auth(token)


@pytest.fixture(scope='session')
def token_2():
    return get_jwt(username='user2@shipchain.io', sub=USER_2_ID, organization_id=ORGANIZATION_2_ID)


@pytest.fixture(scope='session')
def user_2(token_2):
    return passive_credentials_auth(token_2)


@pytest.fixture(scope='session')
def shipper_token():
    return get_jwt(username='shipper1@shipchain.io', sub=SHIPPER_ID, organization_id=ORGANIZATION_ID)


@pytest.fixture(scope='session')
def shipper_user(shipper_token):
    return passive_credentials_auth(shipper_token)


@pytest.fixture(scope='session')
def api_client(user, token):
    client = APIClient()
    client.force_authenticate(user=user, token=token)
    return client


@pytest.fixture(scope='session')
def shipper_api_client(shipper_user, shipper_token):
    client = APIClient()
    client.force_authenticate(user=shipper_user, token=shipper_token)
    return client


@pytest.fixture(scope='session')
def user2_api_client(user_2, token_2):
    client = APIClient()
    client.force_authenticate(user=user_2, token=token_2)
    return client


@pytest.fixture
def mocked_is_shipper(shipper_user, http_pretty, shipment):
    http_pretty.register_uri(http_pretty.GET,
                             f"{test_settings.PROFILES_URL}/api/v1/wallet/{shipment.shipper_wallet_id}/?is_active",
                             body=json.dumps({'good': 'good'}), status=status.HTTP_200_OK)
    return shipper_user

@pytest.fixture
def mocked_storage_credential(http_pretty, shipment):
    http_pretty.register_uri(http_pretty.GET,
                             f"{test_settings.PROFILES_URL}/api/v1/storage_credentials/"
                             f"{shipment.storage_credentials_id}/?is_active", body=json.dumps({'good': 'good'}),
                             status=status.HTTP_200_OK)

@pytest.fixture
def mocked_not_shipper(http_pretty, shipment):
    http_pretty.register_uri(http_pretty.GET,
                             f"{test_settings.PROFILES_URL}/api/v1/wallet/{shipment.shipper_wallet_id}/?is_active",
                             body=json.dumps({'bad': 'bad'}), status=status.HTTP_403_FORBIDDEN)


@pytest.fixture
def mocked_not_carrier(http_pretty, shipment):
    http_pretty.register_uri(http_pretty.GET,
                             f"{test_settings.PROFILES_URL}/api/v1/wallet/{shipment.carrier_wallet_id}/?is_active",
                             body=json.dumps({'bad': 'bad'}), status=status.HTTP_403_FORBIDDEN)


@pytest.fixture
def mocked_not_moderator(http_pretty, shipment):
    http_pretty.register_uri(http_pretty.GET,
                             f"{test_settings.PROFILES_URL}/api/v1/wallet/{shipment.moderator_wallet_id}/?is_active",
                             body=json.dumps({'bad': 'bad'}), status=status.HTTP_403_FORBIDDEN)


@pytest.fixture
def mocked_profiles(http_pretty):
    profiles_ids = {
        "shipper_wallet_id": random_id(),
        "carrier_wallet_id": random_id(),
        "storage_credentials_id": random_id()
    }

    http_pretty.register_uri(http_pretty.GET,
                             f"{test_settings.PROFILES_URL}/api/v1/wallet/{profiles_ids['shipper_wallet_id']}/",
                             body=json.dumps({'good': 'good'}), status=status.HTTP_200_OK)
    http_pretty.register_uri(http_pretty.GET,
                             f"{test_settings.PROFILES_URL}/api/v1/wallet/{profiles_ids['carrier_wallet_id']}/",
                             body=json.dumps({'good': 'good'}), status=status.HTTP_200_OK)
    http_pretty.register_uri(http_pretty.GET,
                             f"{test_settings.PROFILES_URL}/api/v1/storage_credentials/{profiles_ids['storage_credentials_id']}/",
                             body=json.dumps({'good': 'good'}), status=status.HTTP_200_OK)
    return profiles_ids


@pytest.fixture
def shipment(mocked_engine_rpc, mocked_iot_api):
    return Shipment.objects.create(vault_id=VAULT_ID,
                                   carrier_wallet_id=random_id(),
                                   shipper_wallet_id=SHIPPER_ID,
                                   storage_credentials_id=random_id(),
                                   owner_id=USER_ID)
