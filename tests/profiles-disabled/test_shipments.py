from unittest import mock
from conf import test_settings_profiles_disabled

from rest_framework import status
from rest_framework.reverse import reverse
from rest_framework.test import APITestCase, APIClient

from apps.shipments.rpc import ShipmentRPCClient
from apps.shipments.models import Location
from tests.utils import create_form_content

VAULT_ID = 'b715a8ff-9299-4c87-96de-a4b0a4a54509'
CARRIER_WALLET_ID = '3716ff65-3d03-4b65-9fd5-43d15380cff9'
SHIPPER_WALLET_ID = '48381c16-432b-493f-9f8b-54e88a84ec0a'
STORAGE_CRED_ID = '77b72202-5bcd-49f4-9860-bc4ec4fee07b'
DEVICE_ID = '332dc6c8-b89e-449e-a802-0bfe760f83ff'
OWNER_ID = '332dc6c8-b89e-449e-a802-0bfe760f83ff'
LOCATION_NAME = "Test Location Name"
LOCATION_NAME_2 = "Second Test Location Name"
LOCATION_CITY = 'City'
LOCATION_STATE = 'State'
LOCATION_NUMBER = '555-555-5555'


class ShipmentAPITests(APITestCase):

    def setUp(self):
        self.client = APIClient()

    def test_shipment_create(self):
        url = reverse('shipment-list', kwargs={'version': 'v1'})

        parameters = {
            '_vault_id': VAULT_ID,
            '_vault_uri': 's3://bucket/' + VAULT_ID,
            '_carrier_wallet_id': CARRIER_WALLET_ID,
            '_shipper_wallet_id': SHIPPER_WALLET_ID,
            '_owner_id': OWNER_ID,
            '_storage_credentials_id': STORAGE_CRED_ID,
            '_async_hash': 'txHash',
        }

        post_data = '''
                    {
                      "data": {
                        "type": "Shipment",
                        "attributes": {
                          "carrier_wallet_id": "<<_carrier_wallet_id>>",
                          "shipper_wallet_id": "<<_shipper_wallet_id>>",
                          "storage_credentials_id": "<<_storage_credentials_id>>",
                          "owner_id": "<<_owner_id>>"
                        }
                      }
                    }
                '''

        # Mock RPC calls
        mock_shipment_rpc_client = ShipmentRPCClient

        mock_shipment_rpc_client.create_vault = mock.Mock(return_value=(parameters['_vault_id'], parameters['_vault_uri']))
        mock_shipment_rpc_client.add_shipment_data = mock.Mock(return_value={'hash': 'txHash'})
        mock_shipment_rpc_client.create_shipment_transaction = mock.Mock(return_value=('version', {}))
        mock_shipment_rpc_client.create_shipment_transaction.__qualname__ = 'ShipmentRPCClient.create_shipment_transaction'
        mock_shipment_rpc_client.sign_transaction = mock.Mock(return_value=({}, 'txHash'))
        mock_shipment_rpc_client.update_vault_hash_transaction = mock.Mock(return_value=({}))
        mock_shipment_rpc_client.update_vault_hash_transaction.__qualname__ = 'ShipmentRPCClient.set_vault_hash_tx'
        mock_shipment_rpc_client.send_transaction = mock.Mock(return_value={
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
            "transactionHash": parameters['_async_hash'],
            "transactionIndex": 0
        })

        response = self.client.post(url, post_data, content_type='application/vnd.api+json')
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)

    def test_shipment_create_with_location(self):
        parameters = {
            '_vault_id': VAULT_ID,
            '_vault_uri': 's3://bucket/' + VAULT_ID,
            '_carrier_wallet_id': CARRIER_WALLET_ID,
            '_shipper_wallet_id': SHIPPER_WALLET_ID,
            '_storage_credentials_id': STORAGE_CRED_ID,
            '_async_hash': 'txHash',
            '_ship_from_location_name': LOCATION_NAME,
        }

        # Mock RPC calls
        mock_shipment_rpc_client = ShipmentRPCClient

        mock_shipment_rpc_client.create_vault = mock.Mock(return_value=(parameters['_vault_id'], parameters['_vault_uri']))
        mock_shipment_rpc_client.add_shipment_data = mock.Mock(return_value={'hash': 'txHash'})
        mock_shipment_rpc_client.create_shipment_transaction = mock.Mock(return_value=('version', {}))
        mock_shipment_rpc_client.create_shipment_transaction.__qualname__ = 'ShipmentRPCClient.create_shipment_transaction'
        mock_shipment_rpc_client.sign_transaction = mock.Mock(return_value=({}, 'txHash'))
        mock_shipment_rpc_client.update_vault_hash_transaction = mock.Mock(return_value=({}))
        mock_shipment_rpc_client.update_vault_hash_transaction.__qualname__ = 'ShipmentRPCClient.set_vault_hash_tx'
        mock_shipment_rpc_client.send_transaction = mock.Mock(return_value={
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
            "transactionHash": parameters['_async_hash'],
            "transactionIndex": 0
        })

        location = Location.objects.create(name=LOCATION_NAME, city=LOCATION_CITY,
                                           state=LOCATION_STATE)

        one_location_profiles_disabled, content_type = create_form_content({'ship_from_location_id': location.id,
                                                                            'carrier_wallet_id': CARRIER_WALLET_ID,
                                                                            'shipper_wallet_id': SHIPPER_WALLET_ID,
                                                                            'storage_credentials_id': STORAGE_CRED_ID,
                                                                            'owner_id': OWNER_ID})

        url = reverse('shipment-list', kwargs={'version': 'v1'})

        response = self.client.post(url, one_location_profiles_disabled, content_type=content_type)
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
