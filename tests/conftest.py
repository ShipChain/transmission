import pytest
from rest_framework.request import ForcedAuthentication
from rest_framework.test import APIClient
from shipchain_common.utils import random_id
from shipchain_common.test_utils import get_jwt, mocked_rpc_response

from apps.authentication import passive_credentials_auth
from apps.shipments.models import Shipment, Device


def fake_get_raw_token(self, header):
    return header.split()[1]


def fake_get_header(self, request):
    return b'JWT dummy'


ForcedAuthentication.get_raw_token = fake_get_raw_token
ForcedAuthentication.get_header = fake_get_header

USER_ID = random_id()
ORGANIZATION_ID = random_id()
VAULT_ID = random_id()
TRANSACTION_HASH = 'txHash'
DEVICE_ID = random_id()


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


@pytest.fixture
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
def mocked_iot_api(mocker):
    return mocker.patch('apps.shipments.iot_client.DeviceAWSIoTClient.update_shadow', return_value=mocked_rpc_response(
        {'data': {'shipmentId': 'dunno yet', 'shipmentState': 'dunno yet'}}))


@pytest.fixture
def shipment(mocked_engine_rpc, mocked_iot_api):
    return Shipment.objects.create(vault_id=VAULT_ID,
                                   carrier_wallet_id=random_id(),
                                   shipper_wallet_id=random_id(),
                                   storage_credentials_id=random_id(),
                                   owner_id=USER_ID)


@pytest.fixture
def shipment_with_device(shipment):
    shipment.device = Device.objects.create(id=DEVICE_ID)
    shipment.save()
    shipment.refresh_from_db(fields=('device',))
    return shipment
