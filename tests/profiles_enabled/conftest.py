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
from django.urls import reverse
from rest_framework import status
from rest_framework.request import ForcedAuthentication
from rest_framework.test import APIClient
from shipchain_common.test_utils import get_jwt, AssertionHelper
from shipchain_common.utils import random_id

from apps.authentication import passive_credentials_auth
from apps.shipments.models import Shipment, Device, PermissionLink

from tests.conftest import FROM_ADDRESS


def fake_get_raw_token(self, header):
    return header.split()[1]


def fake_get_header(self, request):
    return b'JWT dummy'


ForcedAuthentication.get_raw_token = fake_get_raw_token
ForcedAuthentication.get_header = fake_get_header

SHIPPER_ID = random_id()
ORGANIZATION_ALICE_ID = random_id()
ORGANIZATION_BOB_ID = random_id()
ORGANIZATION_BOB_SHIPPER_ID = random_id()
VAULT_ID = random_id()
ORGANIZATION_NAME = 'ShipChain Test'
ORGANIZATION2_NAME = 'Test Organization-2'
BASE_PERMISSIONS = ['user.perm_1', 'user.perm_2', 'user.perm_3']
GTX_PERMISSIONS = ['user.perm_1', 'gtx.shipment_use', 'user.perm_3']


# Alice owns an organization; her org has 2 members total
# -------------------------------------------------------
@pytest.fixture
def user_alice_id():
    return random_id()


@pytest.fixture
def org_id_alice():
    return ORGANIZATION_ALICE_ID


@pytest.fixture
def user_alice(user_alice_id):
    return passive_credentials_auth(
        get_jwt(
            username='alice@shipchain.io',
            sub=user_alice_id,
            organization_id=ORGANIZATION_ALICE_ID,
            organization_name=ORGANIZATION_NAME,
            permissions=BASE_PERMISSIONS
        ))


@pytest.fixture
def client_alice(user_alice):
    api_client = APIClient()
    api_client.force_authenticate(user_alice)
    return api_client

@pytest.fixture
def user_alice_throttled(user_alice_id):
    return passive_credentials_auth(
        get_jwt(
            username='alice@shipchain.io',
            sub=user_alice_id,
            organization_id=ORGANIZATION_ALICE_ID,
            organization_name=ORGANIZATION_NAME,
            permissions=BASE_PERMISSIONS,
            monthly_rate_limit=1
        ))


@pytest.fixture
def client_alice_throttled(user_alice_throttled):
    api_client = APIClient()
    api_client.force_authenticate(user_alice_throttled)
    return api_client

@pytest.fixture
def user_alice_limited(user_alice_id):
    return passive_credentials_auth(
        get_jwt(
            username='alice@shipchain.io',
            sub=user_alice_id,
            organization_id=ORGANIZATION_ALICE_ID,
            organization_name=ORGANIZATION_NAME,
            permissions=BASE_PERMISSIONS,
            limits={'shipments': {'active': 1, 'documents': 1}}
        ))


@pytest.fixture
def client_alice_limited(user_alice_limited):
    api_client = APIClient()
    api_client.force_authenticate(user_alice_limited)
    return api_client

# Carol is in Alice's organization
# --------------------------------
@pytest.fixture
def user_carol_id():
    return random_id()


@pytest.fixture
def user_carol(user_carol_id):
    return passive_credentials_auth(
        get_jwt(
            username='carol@shipchain.io',
            sub=user_carol_id,
            organization_id=ORGANIZATION_ALICE_ID,
            organization_name=ORGANIZATION_NAME,
            permissions=BASE_PERMISSIONS,
            background_data_hash_interval=25,
            manual_update_hash_interval=30,
        ))


@pytest.fixture
def client_carol(user_carol):
    api_client = APIClient()
    api_client.force_authenticate(user_carol)
    return api_client

@pytest.fixture
def user_carol_throttled(user_carol_id):
    return passive_credentials_auth(
        get_jwt(
            username='carol@shipchain.io',
            sub=user_carol_id,
            organization_id=ORGANIZATION_ALICE_ID,
            organization_name=ORGANIZATION_NAME,
            permissions=BASE_PERMISSIONS,
            background_data_hash_interval=25,
            manual_update_hash_interval=30,
            monthly_rate_limit=1
        ))

@pytest.fixture
def client_carol_throttled(user_carol_throttled):
    api_client = APIClient()
    api_client.force_authenticate(user_carol_throttled)
    return api_client

# Bob has an organization; There are no other members
# ---------------------------------------------------
@pytest.fixture
def user_bob_id():
    return random_id()


@pytest.fixture
def user_bob(user_bob_id):
    return passive_credentials_auth(
        get_jwt(username='bob@shipchain.io',
                sub=user_bob_id,
                organization_id=ORGANIZATION_BOB_ID,
                organization_name=ORGANIZATION2_NAME
                ))


@pytest.fixture
def org_id_bob():
    return ORGANIZATION_BOB_ID


@pytest.fixture
def client_bob(user_bob):
    api_client = APIClient()
    api_client.force_authenticate(user_bob)
    return api_client


# Lionel is alone; He has no organization
# ---------------------------------------
@pytest.fixture
def user_lionel_id():
    return random_id()


@pytest.fixture
def user_lionel(user_lionel_id):
    return passive_credentials_auth(get_jwt(username='lionel@shipchain.io', sub=user_lionel_id))


@pytest.fixture
def client_lionel(user_lionel):
    api_client = APIClient()
    api_client.force_authenticate(user_lionel)
    return api_client


@pytest.fixture
def user_gtx_alice(user_alice_id):
    return passive_credentials_auth(
        get_jwt(username='user1@shipchain.io',
                sub=user_alice_id,
                organization_id=ORGANIZATION_ALICE_ID,
                permissions=GTX_PERMISSIONS,
                features={'gtx': ['shipment_use']}
                ))


@pytest.fixture
def client_gtx_alice(user_gtx_alice):
    api_client = APIClient()
    api_client.force_authenticate(user_gtx_alice)
    return api_client


@pytest.fixture(scope='session')
def gtx_user(gtx_token):
    return passive_credentials_auth(gtx_token)


@pytest.fixture(scope='session')
def shipper_user():
    return passive_credentials_auth(get_jwt(username='shipper1@shipchain.io', sub=SHIPPER_ID))


@pytest.fixture(scope='session')
def gtx_api_client(gtx_user, gtx_token):
    client = APIClient()
    client.force_authenticate(user=gtx_user, token=gtx_token)
    return client


@pytest.fixture(scope='session')
def shipper_api_client(shipper_user):
    client = APIClient()
    client.force_authenticate(shipper_user)
    return client


@pytest.fixture
def mocked_is_shipper(shipper_user, modified_http_pretty, shipment):
    modified_http_pretty.register_uri(modified_http_pretty.GET,
                                      f"{test_settings.PROFILES_URL}/api/v1/wallet/{shipment.shipper_wallet_id}/?is_active",
                                      body=json.dumps({'good': 'good'}), status=status.HTTP_200_OK)
    return modified_http_pretty


@pytest.fixture
def mocked_storage_credential(modified_http_pretty, shipment):
    modified_http_pretty.register_uri(modified_http_pretty.GET,
                             f"{test_settings.PROFILES_URL}/api/v1/storage_credentials/"
                             f"{shipment.storage_credentials_id}/?is_active", body=json.dumps({'good': 'good'}),
                             status=status.HTTP_200_OK)
    return modified_http_pretty


@pytest.fixture
def mocked_not_shipper(modified_http_pretty, shipment):
    modified_http_pretty.register_uri(modified_http_pretty.GET,
                                      f"{test_settings.PROFILES_URL}/api/v1/wallet/{shipment.shipper_wallet_id}/?is_active",
                                      body=json.dumps({'bad': 'bad'}), status=status.HTTP_403_FORBIDDEN)
    return modified_http_pretty

@pytest.fixture
def mocked_not_carrier(modified_http_pretty, shipment):
    modified_http_pretty.register_uri(modified_http_pretty.GET,
                             f"{test_settings.PROFILES_URL}/api/v1/wallet/{shipment.carrier_wallet_id}/?is_active",
                             body=json.dumps({'bad': 'bad'}), status=status.HTTP_403_FORBIDDEN)
    return modified_http_pretty


@pytest.fixture
def mocked_not_moderator(modified_http_pretty, shipment):
    modified_http_pretty.register_uri(modified_http_pretty.GET,
                                      f"{test_settings.PROFILES_URL}/api/v1/wallet/{shipment.moderator_wallet_id}/?is_active",
                                      body=json.dumps({'bad': 'bad'}), status=status.HTTP_403_FORBIDDEN)
    return modified_http_pretty


@pytest.fixture
def nonsuccessful_wallet_owner_calls_assertions(profiles_ids):
    return [
        {
            'path': f'/api/v1/wallet/{profiles_ids["shipper_wallet_id"]}/',
            'body': '',
            'host': test_settings.PROFILES_URL.replace('http://', ''),
        }, {
            'path': f'/api/v1/wallet/{profiles_ids["carrier_wallet_id"]}/',
            'body': '',
            'host': test_settings.PROFILES_URL.replace('http://', ''),
        },
    ]


@pytest.fixture
def mock_non_wallet_owner_calls(modified_http_pretty, profiles_ids):
    wallet_url = f'{test_settings.PROFILES_URL}/api/v1/wallet/'
    storage_credentials_url = f'{test_settings.PROFILES_URL}/api/v1/storage_credentials/' \
                              f'{profiles_ids["storage_credentials_id"]}/'
    modified_http_pretty.register_uri(modified_http_pretty.GET, wallet_url + profiles_ids["shipper_wallet_id"] + "/",
                                      status=status.HTTP_404_NOT_FOUND)
    modified_http_pretty.register_uri(modified_http_pretty.GET, wallet_url + profiles_ids["carrier_wallet_id"] + "/",
                                      status=status.HTTP_404_NOT_FOUND)
    modified_http_pretty.register_uri(modified_http_pretty.GET, storage_credentials_url,
                                      status=status.HTTP_404_NOT_FOUND)

    return modified_http_pretty


@pytest.fixture
def successful_wallet_owner_calls_assertions(profiles_ids):
    return [
        {
            'path': f'/api/v1/wallet/{profiles_ids["shipper_wallet_id"]}/',
            'body': '',
            'host': test_settings.PROFILES_URL.replace('http://', ''),
        },
    ]


@pytest.fixture
def successful_shipment_create_profiles_assertions(profiles_ids):
    return [
        {
            'path': f'/api/v1/storage_credentials/{profiles_ids["storage_credentials_id"]}/',
            'body': '',
            'host': test_settings.PROFILES_URL.replace('http://', ''),
        },
        {
            'path': f'/api/v1/wallet/{profiles_ids["shipper_wallet_id"]}/',
            'body': '',
            'host': test_settings.PROFILES_URL.replace('http://', ''),
        },
    ]


@pytest.fixture
def mock_successful_wallet_owner_calls(modified_http_pretty, profiles_ids):
    wallet_url = f'{test_settings.PROFILES_URL}/api/v1/wallet/'
    storage_credentials_url = f'{test_settings.PROFILES_URL}/api/v1/storage_credentials/' \
                              f'{profiles_ids["storage_credentials_id"]}/?is_active'
    modified_http_pretty.register_uri(modified_http_pretty.GET,
                                      f'{wallet_url}{profiles_ids["shipper_wallet_id"]}/?is_active',
                                      status=status.HTTP_200_OK)
    modified_http_pretty.register_uri(modified_http_pretty.GET,
                                      f'{wallet_url}{profiles_ids["carrier_wallet_id"]}/?is_active',
                                      status=status.HTTP_200_OK)
    modified_http_pretty.register_uri(modified_http_pretty.GET, storage_credentials_url, status=status.HTTP_200_OK)

    return modified_http_pretty


@pytest.fixture
def mocked_profiles(modified_http_pretty, profiles_ids):
    modified_http_pretty.register_uri(modified_http_pretty.GET,
                             f"{test_settings.PROFILES_URL}/api/v1/wallet/{profiles_ids['shipper_wallet_id']}/",
                             body=json.dumps({'data': {'attributes': {'address':  FROM_ADDRESS}}}), status=status.HTTP_200_OK)
    modified_http_pretty.register_uri(modified_http_pretty.GET,
                             f"{test_settings.PROFILES_URL}/api/v1/wallet/{profiles_ids['carrier_wallet_id']}/",
                             body=json.dumps({'good': 'good'}), status=status.HTTP_200_OK)
    modified_http_pretty.register_uri(modified_http_pretty.GET,
                             f"{test_settings.PROFILES_URL}/api/v1/storage_credentials/{profiles_ids['storage_credentials_id']}/",
                             body=json.dumps({'good': 'good'}), status=status.HTTP_200_OK)
    return modified_http_pretty


@pytest.fixture
def mocked_profiles_wallet_list(modified_http_pretty):
    modified_http_pretty.register_uri(modified_http_pretty.GET,
                                      f"{test_settings.PROFILES_URL}/api/v1/wallet",
                                      body=json.dumps({'data': []}), status=status.HTTP_200_OK)
    return modified_http_pretty


@pytest.fixture
def profiles_wallet_list_assertions():
    return [{
            'path': f'/api/v1/wallet',
            'body': '',
            'host': test_settings.PROFILES_URL.replace('http://', ''),
            'query': {'page_size': 9999}
        }]


@pytest.fixture
def shipment(mocked_engine_rpc, mocked_iot_api, user_alice_id, profiles_ids):
    return Shipment.objects.create(vault_id=VAULT_ID,
                                   carrier_wallet_id=profiles_ids['carrier_wallet_id'],
                                   shipper_wallet_id=profiles_ids['shipper_wallet_id'],
                                   storage_credentials_id=profiles_ids['storage_credentials_id'],
                                   owner_id=user_alice_id)


@pytest.fixture
def second_shipment(mocked_engine_rpc, mocked_iot_api):
    return Shipment.objects.create(vault_id=VAULT_ID,
                                   carrier_wallet_id=random_id(),
                                   shipper_wallet_id=SHIPPER_ID,
                                   storage_credentials_id=random_id(),
                                   owner_id=ORGANIZATION_ALICE_ID)


@pytest.fixture
def shipment_bob(mocked_engine_rpc, mocked_iot_api):
    return Shipment.objects.create(vault_id=VAULT_ID,
                                   carrier_wallet_id=random_id(),
                                   shipper_wallet_id=ORGANIZATION_BOB_SHIPPER_ID,
                                   storage_credentials_id=random_id(),
                                   owner_id=ORGANIZATION_BOB_ID)


@pytest.fixture
def shipment_alice(mocked_engine_rpc, mocked_iot_api, profiles_ids):
    return Shipment.objects.create(vault_id=VAULT_ID,
                                   carrier_wallet_id=profiles_ids["carrier_wallet_id"],
                                   shipper_wallet_id=profiles_ids["shipper_wallet_id"],
                                   storage_credentials_id=profiles_ids["storage_credentials_id"],
                                   owner_id=ORGANIZATION_ALICE_ID)


@pytest.fixture
def shipment_alice_two(mocked_engine_rpc, mocked_iot_api, profiles_ids):
    return Shipment.objects.create(vault_id=VAULT_ID,
                                   carrier_wallet_id=profiles_ids["carrier_wallet_id"],
                                   shipper_wallet_id=profiles_ids["shipper_wallet_id"],
                                   storage_credentials_id=profiles_ids["storage_credentials_id"],
                                   owner_id=ORGANIZATION_ALICE_ID)


@pytest.fixture
def url_shipment_alice(shipment_alice):
    return reverse('shipment-detail', kwargs={'version': 'v1', 'pk': shipment_alice.id})


@pytest.fixture
def url_shipment_alice_two(shipment_alice_two):
    return reverse('shipment-detail', kwargs={'version': 'v1', 'pk': shipment_alice_two.id})


@pytest.fixture
def entity_ref_shipment_alice(shipment_alice):
    return AssertionHelper.EntityRef(resource='Shipment', pk=shipment_alice.id)


@pytest.fixture
def entity_ref_shipment_alice_two(shipment_alice_two):
    return AssertionHelper.EntityRef(resource='Shipment', pk=shipment_alice_two.id)


@pytest.fixture
@mock_iot
def mocked_iot(boto):
    return boto.client('iot', region_name='us-east-1')


@pytest.fixture
@mock_iot
def device(mocked_iot):
    device_id = random_id()
    # Create device 'thing'
    mocked_iot.create_thing(
        thingName=device_id
    )

    # Load device cert into AWS
    with open('tests/data/cert.pem', 'r') as cert_file:
        cert_pem = cert_file.read()
    cert_response = mocked_iot.register_certificate(
        certificatePem=cert_pem,
        status='ACTIVE'
    )
    certificate_id = cert_response['certificateId']

    return Device.objects.create(id=device_id, certificate_id=certificate_id)


@pytest.fixture
@mock_iot
def device_two(mocked_iot):
    device_id = random_id()
    # Create device 'thing'
    mocked_iot.create_thing(
        thingName=device_id
    )

    # Load device cert into AWS
    with open('tests/data/cert.pem', 'r') as cert_file:
        cert_pem = cert_file.read()
    cert_response = mocked_iot.register_certificate(
        certificatePem=cert_pem,
        status='ACTIVE'
    )
    certificate_id = cert_response['certificateId']

    return Device.objects.create(id=device_id, certificate_id=certificate_id)


@pytest.fixture
def shipment_alice_with_device(mocked_engine_rpc, mocked_iot_api, device, user_alice_id, profiles_ids):
    return Shipment.objects.create(vault_id=VAULT_ID,
                                   carrier_wallet_id=profiles_ids['carrier_wallet_id'],
                                   shipper_wallet_id=profiles_ids['shipper_wallet_id'],
                                   storage_credentials_id=profiles_ids['storage_credentials_id'],
                                   owner_id=user_alice_id,
                                   device=device)


@pytest.fixture
def permission_link_device_shipment(shipment_alice_with_device):
    return PermissionLink.objects.create(
        expiration_date=datetime.now(timezone.utc) + timedelta(days=1),
        shipment=shipment_alice_with_device
    )


@pytest.fixture
def permission_link_device_shipment_expired(shipment_alice_with_device):
    return PermissionLink.objects.create(
        expiration_date=datetime.now(timezone.utc) - timedelta(days=1),
        shipment=shipment_alice_with_device
    )


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
