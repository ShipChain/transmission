import json
from datetime import datetime, timedelta
from unittest import mock

import httpretty
from django.conf import settings as test_settings
from django.core.cache import cache
from freezegun import freeze_time
from rest_framework import status
from rest_framework.reverse import reverse
from rest_framework.test import APITestCase, APIClient
from shipchain_common.test_utils import get_jwt, replace_variables_in_string

from apps.authentication import passive_credentials_auth
from apps.shipments.rpc import Load110RPCClient

OWNER_ID = '332dc6c8-b89e-449e-a802-0bfe760f83ff'
OWNER_ID_2 = '48381c16-432b-493f-9f8b-54e88a84ec0a'
OWNER_ID_3 = '6165f048-67dc-4265-a231-09ed12afb4e2'
ORGANIZATION_ID = '00000000-0000-0000-0000-000000000002'
MONTHLY_THROTTLE_RATE = 1
VAULT_ID = 'b715a8ff-9299-4c87-96de-a4b0a4a54509'
CARRIER_WALLET_ID = '3716ff65-3d03-4b65-9fd5-43d15380cff9'
SHIPPER_WALLET_ID = '48381c16-432b-493f-9f8b-54e88a84ec0a'
STORAGE_CRED_ID = '77b72202-5bcd-49f4-9860-bc4ec4fee07b'


class ShipmentAPITests(APITestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()

        self.token = get_jwt(username='user1@shipchain.io', sub=OWNER_ID, organization_id=ORGANIZATION_ID,
                             monthly_rate_limit=MONTHLY_THROTTLE_RATE)
        self.token2 = get_jwt(username='user2@shipchain.io', sub=OWNER_ID_2)
        self.token3 = get_jwt(username='user3@shipchain.io', sub=OWNER_ID_3, organization_id=ORGANIZATION_ID,
                              monthly_rate_limit=MONTHLY_THROTTLE_RATE)
        self.user_1 = passive_credentials_auth(self.token)
        self.user_2 = passive_credentials_auth(self.token2)
        self.user_3 = passive_credentials_auth(self.token3)

    def set_user(self, user, token=None):
        self.client.force_authenticate(user=user, token=token)

    @httpretty.activate
    def test_throttling(self):
        self.set_user(self.user_1, self.token)
        url = reverse('shipment-list', kwargs={'version': 'v1'})
        parameters = {
            '_vault_id': VAULT_ID,
            '_vault_uri': 's3://bucket/' + VAULT_ID,
            '_carrier_wallet_id': CARRIER_WALLET_ID,
            '_shipper_wallet_id': SHIPPER_WALLET_ID,
            '_storage_credentials_id': STORAGE_CRED_ID,
            '_async_hash': 'txHash'
        }

        post_data = '''
            {
              "data": {
                "type": "Shipment",
                "attributes": {
                  "carrier_wallet_id": "<<_carrier_wallet_id>>",
                  "shipper_wallet_id": "<<_shipper_wallet_id>>",
                  "storage_credentials_id": "<<_storage_credentials_id>>"
                }
              }
            }
        '''
        httpretty.register_uri(httpretty.GET,
                               f"{test_settings.PROFILES_URL}/api/v1/wallet",
                               body=json.dumps({'data': []}), status=status.HTTP_200_OK)
        httpretty.register_uri(httpretty.GET,
                               f"{test_settings.PROFILES_URL}/api/v1/wallet/{parameters['_shipper_wallet_id']}/",
                               body=json.dumps({'good': 'good'}), status=status.HTTP_200_OK)
        httpretty.register_uri(httpretty.GET,
                               f"{test_settings.PROFILES_URL}/api/v1/storage_credentials/{parameters['_storage_credentials_id']}/",

                               body=json.dumps({'good': 'good'}), status=status.HTTP_200_OK)

        # Mock RPC calls
        mock_shipment_rpc_client = Load110RPCClient

        mock_shipment_rpc_client.create_vault = mock.Mock(return_value=(parameters['_vault_id'], parameters['_vault_uri']))
        mock_shipment_rpc_client.add_shipment_data = mock.Mock(return_value={'hash': 'txHash'})
        mock_shipment_rpc_client.create_shipment_transaction = mock.Mock(return_value=('version', {}))
        mock_shipment_rpc_client.create_shipment_transaction.__qualname__ = 'Load110RPCClient.create_shipment_transaction'
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

        post_data = replace_variables_in_string(post_data, parameters)

        # First call should succeed
        response = self.client.post(url, post_data, content_type='application/vnd.api+json')
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)

        # Calls exceeding the throttle should fail
        response = self.client.post(url, post_data, content_type='application/vnd.api+json')
        self.assertEqual(response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)

        # GET Calls should still succeed
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Calls exceeding the throttle should fail for any member in the org
        self.set_user(self.user_3, self.token3)
        response = self.client.post(url, post_data, content_type='application/vnd.api+json')
        self.assertEqual(response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)

        one_month_later = datetime.now() + timedelta(days=32)

        with freeze_time(one_month_later):
            # First call should succeed
            response = self.client.post(url, post_data, content_type='application/vnd.api+json')
            self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)

            # Calls exceeding the throttle should fail
            response = self.client.post(url, post_data, content_type='application/vnd.api+json')
            self.assertEqual(response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)

        # Call for someone not in an org should succeed
        self.set_user(self.user_2, self.token2)
        response = self.client.post(url, post_data, content_type='application/vnd.api+json')
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
