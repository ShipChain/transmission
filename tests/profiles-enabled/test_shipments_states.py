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
from datetime import datetime
from dateutil.parser import parse as dt_parse
from dateutil.relativedelta import relativedelta

import json
import pytz
import pytest
from rest_framework import status
from rest_framework.reverse import reverse
from rest_framework.test import APIClient

from apps.authentication import passive_credentials_auth
from apps.shipments.models import Shipment, TransitState
from apps.utils import random_id
from tests.utils import get_jwt

USER_ID = random_id()
ORGANIZATION_ID = random_id()
VAULT_ID = random_id()
TRANSACTION_HASH = 'txHash'


@pytest.fixture(scope='session')
def token():
    return get_jwt(username='user1@shipchain.io', sub=USER_ID, organization_id=ORGANIZATION_ID)


@pytest.fixture(scope='session')
def user(token):
    return passive_credentials_auth(token)


@pytest.fixture(scope='session')
def api_client(user, token):
    client = APIClient()
    client.force_authenticate(user=user, token=token)
    return client


@pytest.fixture()
def mocked_engine_rpc(mocker):
    mocker.patch('apps.shipments.rpc.Load110RPCClient.create_vault', return_value=(VAULT_ID, 's3://fake-vault-uri/'))
    mocker.patch('apps.shipments.rpc.Load110RPCClient.add_shipment_data', return_value={'hash': TRANSACTION_HASH})
    mocked_cst = mocker.patch('apps.shipments.rpc.Load110RPCClient.create_shipment_transaction',
                              return_value=('version', {}))
    mocked_cst.__qualname__ = 'ShipmentRPCClient.create_shipment_transaction'
    mocker.patch('apps.shipments.rpc.Load110RPCClient.sign_transaction', return_value=('version', {}))
    mocked_uvht = mocker.patch('apps.shipments.rpc.Load110RPCClient.set_vault_hash_tx', return_value={})
    mocked_uvht.__qualname__ = 'ShipmentRPCClient.set_vault_hash_tx'
    mocker.patch('apps.shipments.rpc.Load110RPCClient.send_transaction', return_value={
        "blockHash": "0xccb595947a121e37df8bf689c3f88c6d9c7fb56070c9afda38551540f9e231f7",
        "blockNumber": 15,
        "contractAddress": None,
        "cumulativeGasUsed": 138090,
        "from": "0x13b1eebb31a1aa2ecaa2ad9e7455df2f717f2143",
        "gasUsed": 138090,
        "logs": [],
        "logsBloom": "0x0000000000",
        "status": True,
        "to": "0x25ff5dc79a7c4e34254ff0f4a19d69e491201dd3",
        "transactionHash": TRANSACTION_HASH,
        "transactionIndex": 0
    })


@pytest.fixture
def shipment(mocked_engine_rpc):
    return Shipment.objects.create(vault_id=VAULT_ID,
                                   carrier_wallet_id=random_id(),
                                   shipper_wallet_id=random_id(),
                                   storage_credentials_id=random_id(),
                                   owner_id=USER_ID)


@pytest.mark.django_db
def test_protected_shipment_date_updates(api_client, shipment):
    url = reverse('shipment-detail', kwargs={'version': 'v1', 'pk': shipment.id})

    start_date = datetime.utcnow().replace(tzinfo=pytz.UTC) - relativedelta(years=1)
    parameters = {
        'pickup_est': start_date.isoformat(),
        'pickup_act': (start_date + relativedelta(days=1)).isoformat(),
        'port_arrival_est': (start_date + relativedelta(days=2)).isoformat(),
        'port_arrival_act': (start_date + relativedelta(days=3)).isoformat(),
        'delivery_est': (start_date + relativedelta(days=4)).isoformat(),
        'delivery_act': (start_date + relativedelta(days=5)).isoformat(),
    }
    # Assert that none of the values to be updated already exist
    for field in parameters:
        assert getattr(shipment, field) != parameters[field], f'Field: {field}'

    response = api_client.patch(url, data=json.dumps(parameters), content_type='application/json')
    assert response.status_code == status.HTTP_202_ACCEPTED
    updated_parameters = response.json()['data']['attributes']

    # Assert that only the updatable fields got updated
    for field in parameters:
        if '_act' in field:
            assert updated_parameters[field] is None, f'Field: {field}'
        else:
            assert dt_parse(parameters[field]) == dt_parse(updated_parameters[field]), f'Field: {field}'
