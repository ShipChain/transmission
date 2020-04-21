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
from shipchain_common.test_utils import get_jwt, AssertionHelper, modified_http_pretty
from shipchain_common.utils import random_id

from apps.authentication import passive_credentials_auth
from apps.shipments.models import Shipment, Device, PermissionLink


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


@pytest.fixture
def user_alice_id():
    return random_id()


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
def org_id_alice():
    return ORGANIZATION_ALICE_ID


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


@pytest.fixture(scope='session')
def user_gtx_alice(user_alice_id):
    return passive_credentials_auth(
        get_jwt(username='user1@shipchain.io',
                sub=user_alice_id,
                organization_id=ORGANIZATION_ALICE_ID,
                permissions=GTX_PERMISSIONS
                ))


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
def profiles_ids():
    return {
        "shipper_wallet_id": random_id(),
        "carrier_wallet_id": random_id(),
        "storage_credentials_id": random_id()
    }


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
def mocked_profiles(http_pretty, profiles_ids):
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
def org2_shipment(mocked_engine_rpc, mocked_iot_api):
    return Shipment.objects.create(vault_id=VAULT_ID,
                                   carrier_wallet_id=random_id(),
                                   shipper_wallet_id=ORGANIZATION_BOB_SHIPPER_ID,
                                   storage_credentials_id=random_id(),
                                   owner_id=ORGANIZATION_BOB_ID)


@pytest.fixture
def shipment_alice(mocked_engine_rpc, mocked_iot_api, user_alice_id, profiles_ids):
    return Shipment.objects.create(vault_id=VAULT_ID,
                                   carrier_wallet_id=profiles_ids["carrier_wallet_id"],
                                   shipper_wallet_id=profiles_ids["shipper_wallet_id"],
                                   storage_credentials_id=profiles_ids["storage_credentials_id"],
                                   owner_id=user_alice_id)


@pytest.fixture
def shipment_alice_two(mocked_engine_rpc, mocked_iot_api, user_alice_id, profiles_ids):
    return Shipment.objects.create(vault_id=VAULT_ID,
                                   carrier_wallet_id=profiles_ids["carrier_wallet_id"],
                                   shipper_wallet_id=profiles_ids["shipper_wallet_id"],
                                   storage_credentials_id=profiles_ids["storage_credentials_id"],
                                   owner_id=user_alice_id)


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
def device_alice_with_shipment(mocked_engine_rpc, mocked_iot_api, device, user_alice_id, profiles_ids):
    Shipment.objects.create(vault_id=VAULT_ID,
                            carrier_wallet_id=profiles_ids['carrier_wallet_id'],
                            shipper_wallet_id=profiles_ids['shipper_wallet_id'],
                            storage_credentials_id=profiles_ids['storage_credentials_id'],
                            owner_id=user_alice_id,
                            device=device)
    return device
