import json
from unittest import mock

from django.conf import settings as test_settings
from rest_framework import status
from rest_framework.reverse import reverse
from rest_framework.test import APITestCase

from apps.eth.models import TransactionReceipt, EthAction
from apps.eth.rpc import EventRPCClient
from apps.jobs.models import AsyncJob
from apps.shipments.models import Shipment
from apps.shipments.rpc import Load110RPCClient

BLOCK_HASH = "0x38823cb26b528867c8dbea4146292908f55e1ee7f293685db1df0851d1b93b24"
BLOCK_NUMBER = 14
CUMULATIVE_GAS_USED = 270710
FROM_ADDRESS = "0x13b1eebb31a1aa2ecaa2ad9e7455df2f717f2143"
FROM_ADDRESS_2 = "0xd8A3ba60e1a5a742781C055C63796ffCa3a43e85"
GAS_USED = 270710
LOGS = [{"address": "0x25Ff5dc79A7c4e34254ff0f4a19d69E491201DD3"}]
LOGS_BLOOM = "0x0000000000000000000000000000000...00000000000000000000"
STATUS = True
TO_ADDRESS = "0x25ff5dc79a7c4e34254ff0f4a19d69e491201dd3"
TRANSACTION_HASH = "0x7ff1a69326d64507a306a836128aa67503972cb38e22fa6db217ec553c560d76"
TRANSACTION_HASH_2 = "0x7ff1a69326d64507a306a836128aa67503972cb38e22fa6db217ec553c560d77"
TRANSACTION_INDEX = 0
WALLET_ID = "1243d23b-e2fc-475a-8290-0e4f53479553"
USER_ID = '00000000-0000-0000-0000-000000000000'


class TransactionReceiptTestCase(APITestCase):
    def createAsyncJobs(self, shipment):
        self.asyncJobs = []
        self.asyncJobs.append(AsyncJob.objects.create(shipment=shipment))

    def createEthAction(self, listener):
        self.ethActions = []
        self.ethActions.append(EthAction.objects.create(transaction_hash=TRANSACTION_HASH, async_job=self.asyncJobs[0],
                                                        shipment=listener))
        self.ethActions.append(EthAction.objects.create(transaction_hash=TRANSACTION_HASH_2,
                                                        async_job=self.asyncJobs[0], shipment=listener))

    def createTransactionReceipts(self):
        self.transactionReceipts = []
        self.transactionReceipts.append(TransactionReceipt.objects.create(block_hash=BLOCK_HASH,
                                                                          cumulative_gas_used=CUMULATIVE_GAS_USED,
                                                                          block_number=BLOCK_NUMBER,
                                                                          from_address=FROM_ADDRESS,
                                                                          gas_used=GAS_USED,
                                                                          logs=LOGS,
                                                                          logs_bloom=LOGS_BLOOM,
                                                                          status=STATUS,
                                                                          to_address=TO_ADDRESS,
                                                                          eth_action=self.ethActions[0]))
        self.transactionReceipts.append(TransactionReceipt.objects.create(block_hash=BLOCK_HASH,
                                                                          cumulative_gas_used=CUMULATIVE_GAS_USED,
                                                                          block_number=BLOCK_NUMBER,
                                                                          from_address=FROM_ADDRESS_2,
                                                                          gas_used=GAS_USED,
                                                                          logs=LOGS,
                                                                          logs_bloom=LOGS_BLOOM,
                                                                          status=STATUS,
                                                                          to_address=TO_ADDRESS,
                                                                          eth_action=self.ethActions[1]))

    def test_transaction_get(self):
        mock_shipment_rpc_client = Load110RPCClient

        mock_shipment_rpc_client.create_vault = mock.Mock(
            return_value=(WALLET_ID, 's3://bucket/' + WALLET_ID))
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
            "transactionHash": TRANSACTION_HASH,
            "transactionIndex": 0
        })

        listener = Shipment.objects.create(owner_id=USER_ID, carrier_wallet_id=WALLET_ID,
                                           shipper_wallet_id=WALLET_ID, vault_id=WALLET_ID,
                                           storage_credentials_id=WALLET_ID,
                                           )

        self.createAsyncJobs(listener)
        self.createEthAction(listener)
        self.createTransactionReceipts()

        url = reverse('transaction-detail', kwargs={'pk': TRANSACTION_HASH, 'version': 'v1'})

        response = self.client.get(url)
        response_json = response.json()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response_json['included'][1]['attributes']['from_address'], FROM_ADDRESS)

    def test_transaction_list(self):
        listener, _ = Shipment.objects.get_or_create(
            id='FAKE_LISTENER_ID',
            owner_id=USER_ID,
            storage_credentials_id='FAKE_STORAGE_CREDENTIALS_ID',
            shipper_wallet_id='FAKE_SHIPPER_WALLET_ID',
            carrier_wallet_id='FAKE_CARRIER_WALLET_ID',
            contract_version='1.0.0',
        )

        self.createAsyncJobs(listener)
        self.createEthAction(listener)
        self.createTransactionReceipts()

        # Ensure two different transaction receipts were created
        self.assertEqual(TransactionReceipt.objects.count(), 2)

        url = reverse('transaction-list', kwargs={'version': 'v1'})

        # Request without wallet_address query field should fail
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        # request for specific eth_actions should succeed
        response = self.client.get(f'{url}?wallet_address={FROM_ADDRESS}')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Request with wallet_id should fail
        response = self.client.get(f'{url}?wallet_id={WALLET_ID}')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_engine_subscribe_generic(self):
        from apps.rpc_client import requests
        from tests.utils import mocked_rpc_response

        mock_shipment_rpc = EventRPCClient()

        params = {
            "url": "URL",
            "project": "LOAD",
            "interval": 5000,
            "eventNames": ["allEvents"]
        }
        full_params = {
            'jsonrpc': '2.0',
            'id': 0,
            'params': params,
            'method': 'event.subscribe'
        }

        with mock.patch.object(requests.Session, 'post') as mock_method:

            mock_method.return_value = mocked_rpc_response({'result': {'success': True, 'subscription': params}})

            mock_shipment_rpc.subscribe(project="LOAD", url="URL")

            mock_method.assert_called_with(test_settings.ENGINE_RPC_URL, data=json.dumps(full_params))


