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
from datetime import datetime, timezone

import freezegun
import pytest
import requests
from moto import mock_iot
from rest_framework.test import APIClient
from shipchain_common.test_utils import mocked_rpc_response, modified_http_pretty, AssertionHelper
from shipchain_common.utils import random_id

from apps.shipments.models import Shipment, Device

USER_ID = random_id()
SHIPPER_ID = random_id()
VAULT_ID = random_id()
DEVICE_ID = random_id()

TRANSACTION_HASH = 'txHash'
FROM_ADDRESS = "0x13b1eebb31a1aa2ecaa2ad9e7455df2f717f2143"
TO_ADDRESS = "0x25ff5dc79a7c4e34254ff0f4a19d69e491201dd3"
BLOCK_HASH = "0x38823cb26b528867c8dbea4146292908f55e1ee7f293685db1df0851d1b93b24"
BLOCK_NUMBER = 14
CUMULATIVE_GAS_USED = 270710
GAS_USED = 270710
LOGS = [{"address": "0x25Ff5dc79A7c4e34254ff0f4a19d69E491201DD3"}]
LOGS_BLOOM = "0x0000000000000000000000000000000...00000000000000000000"
STATUS = True
TRANSACTION_INDEX = 0

@pytest.fixture(scope='session')
def api_client():
    return APIClient()


@pytest.fixture
def profiles_ids():
    return {
        "shipper_wallet_id": random_id(),
        "carrier_wallet_id": random_id(),
        "storage_credentials_id": random_id()
    }


@pytest.fixture
def mock_requests_session(mocker):
    mocker.patch.object(requests.Session, 'post', return_value=mocked_rpc_response({
        "jsonrpc": "2.0",
        "result": {
            "success": True,
            "vault_id": "TEST_VAULT_ID",
            "vault_uri": "engine://test_url",
            "vault_signed": {'hash': "TEST_VAULT_SIGNATURE"}
        }
    }))


@pytest.fixture
def mocked_engine_rpc(mocker):
    mocker.patch('apps.shipments.rpc.Load110RPCClient.create_vault', return_value=(VAULT_ID, 's3://fake-vault-uri/'))
    mocker.patch('apps.shipments.rpc.Load110RPCClient.add_shipment_data', return_value={'hash': TRANSACTION_HASH})
    mocker.patch('apps.shipments.rpc.Load110RPCClient.add_tracking_data', return_value={'hash': TRANSACTION_HASH})
    mocked_cst = mocker.patch('apps.shipments.rpc.Load110RPCClient.create_shipment_transaction',
                              return_value=('version', {}))
    mocked_cst.__qualname__ = 'Load110RPCClient.create_shipment_transaction'
    mocker.patch('apps.shipments.rpc.Load110RPCClient.sign_transaction', return_value=('version', {}))
    mocked_uvht = mocker.patch('apps.shipments.rpc.Load110RPCClient.set_vault_hash_tx', return_value={})
    mocked_uvht.__qualname__ = 'ShipmentRPCClient.set_vault_hash_tx'
    mocker.patch('apps.shipments.rpc.Load110RPCClient.send_transaction', return_value={
        "blockHash": BLOCK_HASH,
        "blockNumber": BLOCK_NUMBER,
        "contractAddress": None,
        "cumulativeGasUsed": CUMULATIVE_GAS_USED,
        "from": FROM_ADDRESS,
        "gasUsed": GAS_USED,
        "logs": LOGS,
        "logsBloom": LOGS_BLOOM,
        "status": STATUS,
        "to": TO_ADDRESS,
        "transactionHash": TRANSACTION_HASH,
        "transactionIndex": TRANSACTION_INDEX
    })


@pytest.fixture
def mocked_iot_api(mocker):
    return mocker.patch('apps.shipments.iot_client.DeviceAWSIoTClient.update_shadow', return_value=mocked_rpc_response(
        {'data': {'shipmentId': 'dunno yet', 'shipmentState': 'dunno yet'}}))


@pytest.fixture
def shipment(mocked_engine_rpc, mocked_iot_api, profiles_ids):
    return Shipment.objects.create(vault_id=VAULT_ID,
                                   owner_id=USER_ID,
                                   **profiles_ids)


@pytest.fixture
def shipment_with_device(shipment):
    shipment.device = Device.objects.create(id=DEVICE_ID)
    shipment.save()
    shipment.refresh_from_db(fields=('device',))
    return shipment


@pytest.fixture
def second_shipment(mocked_engine_rpc, mocked_iot_api, profiles_ids):
    return Shipment.objects.create(vault_id=random_id(),
                                   owner_id=USER_ID,
                                   **profiles_ids)


@pytest.fixture
def third_shipment(mocked_engine_rpc, mocked_iot_api, profiles_ids):
    return Shipment.objects.create(vault_id=random_id(),
                                   owner_id=USER_ID,
                                   **profiles_ids)


@pytest.fixture(autouse=True)
def enable_db_access_for_all_tests(db):
    pass


@pytest.fixture
def boto():
    import boto3
    boto3.setup_default_session()  # https://github.com/spulec/moto/issues/1926
    return boto3


@pytest.fixture
def entity_shipment_relationship(shipment):
    return AssertionHelper.EntityRef(resource='Shipment', pk=shipment.id)


@pytest.fixture
def current_datetime():
    return datetime.now(timezone.utc)


@pytest.fixture
def frozen_time(current_datetime):
    with freezegun.freeze_time(current_datetime) as current_datetime:
        yield current_datetime
