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
from datetime import datetime, timezone, timedelta

import pytest
from django.conf import settings as test_settings
from moto import mock_iot
from rest_framework import status
from rest_framework.request import ForcedAuthentication
from rest_framework.test import APIClient
from shipchain_common.test_utils import get_jwt
from shipchain_common.utils import random_id

from apps.authentication import passive_credentials_auth
from apps.shipments.models import Shipment, Device, PermissionLink


def fake_get_raw_token(self, header):
    return header.split()[1]


def fake_get_header(self, request):
    return b'JWT dummy'


ForcedAuthentication.get_raw_token = fake_get_raw_token
ForcedAuthentication.get_header = fake_get_header

USER_ID = random_id()
USER2_ID = random_id()
SHIPPER_ID = random_id()
ORGANIZATION2_SHIPPER_ID = random_id()
ORGANIZATION_ID = random_id()
ORGANIZATION2_ID = random_id()
VAULT_ID = random_id()
ORGANIZATION_NAME = 'ShipChain Test'
ORGANIZATION2_NAME = 'Test Organization-2'
BASE_PERMISSIONS = ['user.perm_1', 'user.perm_2', 'user.perm_3']
GTX_PERMISSIONS = ['user.perm_1', 'gtx.shipment_use', 'user.perm_3']


@pytest.fixture(scope='session')
def token():
    return get_jwt(username='user1@shipchain.io',
                   sub=USER_ID,
                   organization_id=ORGANIZATION_ID,
                   organization_name=ORGANIZATION_NAME,
                   permissions=BASE_PERMISSIONS)


@pytest.fixture(scope='session')
def gtx_token():
    return get_jwt(username='user1@shipchain.io', sub=USER_ID, organization_id=ORGANIZATION_ID, permissions=GTX_PERMISSIONS)


@pytest.fixture(scope='session')
def user(token):
    return passive_credentials_auth(token)


@pytest.fixture(scope='session')
def gtx_user(gtx_token):
    return passive_credentials_auth(gtx_token)


@pytest.fixture(scope='session')
def org_id(user):
    return user.token.get('organization_id', None)


@pytest.fixture(scope='session')
def token2():
    return get_jwt(username='user2@shipchain.io',
                   sub=USER2_ID,
                   organization_id=ORGANIZATION2_ID,
                   organization_name=ORGANIZATION2_NAME)


@pytest.fixture(scope='session')
def user2(token2):
    return passive_credentials_auth(token2)


@pytest.fixture(scope='session')
def org2_id(user2):
    return user2.token.get('organization_id', None)


@pytest.fixture(scope='session')
def shipper_token():
    return get_jwt(username='shipper1@shipchain.io', sub=SHIPPER_ID)


@pytest.fixture(scope='session')
def shipper_user(shipper_token):
    return passive_credentials_auth(shipper_token)


@pytest.fixture
def user_alice_id():
    return random_id()


@pytest.fixture
def user_bob_id():
    return random_id()


@pytest.fixture
def no_user_api_client():
    return APIClient()


@pytest.fixture
def client_alice(user_alice_id):
    api_client = APIClient()
    token = get_jwt(username='alice@shipchain.io', sub=user_alice_id, organization_id=random_id())
    api_client.force_authenticate(user=passive_credentials_auth(token), token=token)
    return api_client


@pytest.fixture
def client_bob(user_bob_id):
    api_client = APIClient()
    token = get_jwt(username='bob@shipchain.io', sub=user_bob_id, organization_id=random_id())
    api_client.force_authenticate(user=passive_credentials_auth(token), token=token)
    return api_client


@pytest.fixture(scope='session')
def api_client(user, token):
    client = APIClient()
    client.force_authenticate(user=user, token=token)
    return client


@pytest.fixture(scope='session')
def gtx_api_client(gtx_user, gtx_token):
    client = APIClient()
    client.force_authenticate(user=gtx_user, token=gtx_token)
    return client


@pytest.fixture(scope='session')
def shipper_api_client(shipper_user, shipper_token):
    client = APIClient()
    client.force_authenticate(user=shipper_user, token=shipper_token)
    return client


@pytest.fixture(scope='session')
def user2_api_client(user2, token2):
    client = APIClient()
    client.force_authenticate(user=user2, token=token2)
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
def mock_non_wallet_owner_calls(http_pretty):
    wallet_url = f'{test_settings.PROFILES_URL}/api/v1/wallet/{SHIPPER_ID}/'
    storage_credentials_url = f'{test_settings.PROFILES_URL}/api/v1/storage_credentials/{SHIPPER_ID}/'
    http_pretty.register_uri(http_pretty.GET, wallet_url, status=status.HTTP_404_NOT_FOUND)
    http_pretty.register_uri(http_pretty.GET, wallet_url, status=status.HTTP_404_NOT_FOUND)
    http_pretty.register_uri(http_pretty.GET, storage_credentials_url, status=status.HTTP_404_NOT_FOUND)

    return http_pretty


@pytest.fixture
def mock_successful_wallet_owner_calls(http_pretty):
    wallet_url = f'{test_settings.PROFILES_URL}/api/v1/wallet/{SHIPPER_ID}/'
    storage_credentials_url = f'{test_settings.PROFILES_URL}/api/v1/storage_credentials/{SHIPPER_ID}/'
    http_pretty.register_uri(http_pretty.GET, wallet_url,
                             body=json.dumps({'good': 'good'}), status=status.HTTP_200_OK)
    http_pretty.register_uri(http_pretty.GET, wallet_url,
                             body=json.dumps({'good': 'good'}), status=status.HTTP_200_OK)
    http_pretty.register_uri(http_pretty.GET, storage_credentials_url,
                             body=json.dumps({'good': 'good'}), status=status.HTTP_200_OK)

    return http_pretty


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
                                   carrier_wallet_id=SHIPPER_ID,
                                   shipper_wallet_id=SHIPPER_ID,
                                   storage_credentials_id=SHIPPER_ID,
                                   owner_id=USER_ID)


@pytest.fixture
def second_shipment(mocked_engine_rpc, mocked_iot_api):
    return Shipment.objects.create(vault_id=VAULT_ID,
                                   carrier_wallet_id=random_id(),
                                   shipper_wallet_id=SHIPPER_ID,
                                   storage_credentials_id=random_id(),
                                   owner_id=ORGANIZATION_ID)


@pytest.fixture
def org2_shipment(mocked_engine_rpc, mocked_iot_api):
    return Shipment.objects.create(vault_id=VAULT_ID,
                                   carrier_wallet_id=random_id(),
                                   shipper_wallet_id=ORGANIZATION2_SHIPPER_ID,
                                   storage_credentials_id=random_id(),
                                   owner_id=ORGANIZATION2_ID)


@pytest.fixture
def shipment_alice(mocked_engine_rpc, mocked_iot_api, user_alice_id):
    return Shipment.objects.create(vault_id=VAULT_ID,
                                   carrier_wallet_id=SHIPPER_ID,
                                   shipper_wallet_id=SHIPPER_ID,
                                   storage_credentials_id=SHIPPER_ID,
                                   owner_id=user_alice_id)


@pytest.fixture
@mock_iot
def device(boto):
    device_id = random_id()
    # Create device 'thing'
    iot = boto.client('iot', region_name='us-east-1')
    iot.create_thing(
        thingName=device_id
    )

    # Load device cert into AWS
    with open('tests/data/cert.pem', 'r') as cert_file:
        cert_pem = cert_file.read()
    cert_response = iot.register_certificate(
        certificatePem=cert_pem,
        status='ACTIVE'
    )
    certificate_id = cert_response['certificateId']

    return Device.objects.create(id=device_id, certificate_id=certificate_id)


@pytest.fixture
def shipment_alice_with_device(mocked_engine_rpc, mocked_iot_api, device, user_alice_id):
    return Shipment.objects.create(vault_id=VAULT_ID,
                                   carrier_wallet_id=SHIPPER_ID,
                                   shipper_wallet_id=SHIPPER_ID,
                                   storage_credentials_id=SHIPPER_ID,
                                   owner_id=user_alice_id,
                                   device=device)


@pytest.fixture
def permission_link_device_shipment(shipment_alice_with_device):
    return PermissionLink.objects.create(
        expiration_date=datetime.now(timezone.utc) + timedelta(days=1),
        shipment=shipment_alice_with_device
    )


@pytest.fixture
def device_alice_with_shipment(mocked_engine_rpc, mocked_iot_api, device, user_alice_id):
    Shipment.objects.create(vault_id=VAULT_ID,
                            carrier_wallet_id=SHIPPER_ID,
                            shipper_wallet_id=SHIPPER_ID,
                            storage_credentials_id=SHIPPER_ID,
                            owner_id=user_alice_id,
                            device=device)
    return device
