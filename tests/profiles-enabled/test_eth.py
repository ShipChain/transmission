import datetime
import json
from unittest import mock

import httpretty
from django.conf import settings as test_settings
from rest_framework import status
from rest_framework.reverse import reverse
from rest_framework.test import APITestCase, APIClient, force_authenticate
from shipchain_common.test_utils import get_jwt

from apps.authentication import passive_credentials_auth
from apps.eth.models import TransactionReceipt, EthAction
from apps.jobs.models import AsyncJob
from apps.shipments.models import Shipment, PermissionLink

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

    def setUp(self):
        self.client = APIClient()

        self.token = get_jwt(username='user1@shipchain.io')
        self.user_1 = passive_credentials_auth(self.token)

    def set_user(self, user, token=None):
        self.client.force_authenticate(user=user, token=token)

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
        with mock.patch('apps.shipments.rpc.ShipmentRPCClient.create_vault') as create_vault, \
                mock.patch('apps.shipments.rpc.ShipmentRPCClient.add_shipment_data') as add_shipment_data, \
                mock.patch('apps.shipments.rpc.Load110RPCClient.create_shipment_transaction') as create_shipment_transaction, \
                mock.patch('apps.shipments.rpc.Load110RPCClient.sign_transaction') as sign_transaction, \
                mock.patch('apps.shipments.rpc.Load110RPCClient.set_vault_hash_tx') as set_vault_hash_tx, \
                mock.patch('apps.shipments.rpc.Load110RPCClient.send_transaction') as send_transaction:

            create_vault.return_value = (WALLET_ID, 's3://bucket/' + WALLET_ID)
            add_shipment_data.return_value = {'hash': 'txHash'}
            create_shipment_transaction.return_value = ('version', {})
            create_shipment_transaction.__qualname__ = 'Load110RPCClient.create_shipment_transaction'
            sign_transaction.return_value = ({}, 'txHash')
            set_vault_hash_tx.return_value = ({})
            set_vault_hash_tx.__qualname__ = 'ShipmentRPCClient.set_vault_hash_tx'
            send_transaction.return_value = {
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
            }

            listener = Shipment.objects.create(owner_id=USER_ID, carrier_wallet_id=WALLET_ID,
                                               shipper_wallet_id=WALLET_ID, vault_id=WALLET_ID,
                                               storage_credentials_id=WALLET_ID)

            self.createAsyncJobs(listener)
            self.createEthAction(listener)
            self.createTransactionReceipts()

            url = reverse('transaction-detail', kwargs={'pk': TRANSACTION_HASH, 'version': 'v1'})

            self.set_user(self.user_1)
            response = self.client.get(url)
            response_json = response.json()

            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertEqual(response_json['included'][1]['attributes']['from_address'], FROM_ADDRESS)

    def test_transaction_list(self):
        with mock.patch('apps.shipments.rpc.ShipmentRPCClient.create_vault') as create_vault, \
                mock.patch('apps.shipments.rpc.ShipmentRPCClient.add_shipment_data') as add_shipment_data, \
                mock.patch('apps.shipments.rpc.Load110RPCClient.create_shipment_transaction') as create_shipment_transaction, \
                mock.patch('apps.shipments.rpc.Load110RPCClient.sign_transaction') as sign_transaction, \
                mock.patch('apps.shipments.rpc.Load110RPCClient.set_vault_hash_tx') as set_vault_hash_tx, \
                mock.patch('apps.shipments.rpc.Load110RPCClient.send_transaction') as send_transaction:

            create_vault.return_value = (WALLET_ID, 's3://bucket/' + WALLET_ID)
            add_shipment_data.return_value = {'hash': 'txHash'}
            create_shipment_transaction.return_value = ('version', {})
            create_shipment_transaction.__qualname__ = 'Load110RPCClient.create_shipment_transaction'
            sign_transaction.return_value = ({}, 'txHash')
            set_vault_hash_tx.return_value = ({})
            set_vault_hash_tx.__qualname__ = 'ShipmentRPCClient.set_vault_hash_tx'
            send_transaction.return_value = {
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
            }

            listener = Shipment.objects.create(owner_id=USER_ID, carrier_wallet_id=WALLET_ID,
                                               shipper_wallet_id=WALLET_ID, vault_id=WALLET_ID,
                                               storage_credentials_id=WALLET_ID)

            valid_permission_link = PermissionLink.objects.create(
                expiration_date=datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=1),
                shipment=listener
            )

            invalid_permission_link = PermissionLink.objects.create(
                expiration_date=datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=-1),
                shipment=listener
            )

            self.createAsyncJobs(listener)
            self.createEthAction(listener)
            self.createTransactionReceipts()

            self.set_user(self.user_1, token=self.token)

            # Ensure two different transaction receipts were created
            self.assertEqual(TransactionReceipt.objects.count(), 2)

            url = reverse('transaction-list', kwargs={'version': 'v1'})

            # Request without wallet_address query field should fail
            response = self.client.get(url)
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

            # request for specific eth actions using wallet_address should fail
            response = self.client.get(f'{url}?wallet_address={FROM_ADDRESS}')
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

            with httpretty.enabled():
                httpretty.register_uri(httpretty.GET,
                                       f"{test_settings.PROFILES_URL}/api/v1/wallet/{WALLET_ID}/",
                                       body=json.dumps({'data': {'attributes': {'address':  FROM_ADDRESS}}}),
                                       status=status.HTTP_200_OK)

                # request for specific eth actions should only return ones with that from_address
                response = self.client.get(f'{url}?wallet_id={WALLET_ID}')
                force_authenticate(response, user=self.user_1, token=self.token)
                response_json = response.json()
                self.assertEqual(response.status_code, status.HTTP_200_OK)
                self.assertEqual(len(response_json['data']), 1)

                httpretty.register_uri(httpretty.GET,
                                       f"{test_settings.PROFILES_URL}/api/v1/wallet/{WALLET_ID}/",
                                       status=status.HTTP_401_UNAUTHORIZED)

                # request for specific eth actions should fail if the profiles request fails
                response = self.client.get(f'{url}?wallet_id={WALLET_ID}')
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

            # Shipment transactions list
            nested_url = reverse('shipment-transactions-list', kwargs={'version': 'v1', 'shipment_pk': listener.id})
            response = self.client.get(nested_url)
            self.assertEqual(response.status_code, status.HTTP_200_OK)

            # Ordering works as expected
            response = self.client.get(f'{nested_url}?ordering=-created_at')
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            response_json = response.json()
            self.assertEqual(response_json['data'][0]['attributes']['transaction_hash'], TRANSACTION_HASH_2)

            # A Transactions list view cannot be accessed by an anonymous user on a nested route
            self.set_user(None)

            with mock.patch('apps.permissions.IsShipperMixin.has_shipper_permission') as mock_carrier, \
                    mock.patch('apps.permissions.IsCarrierMixin.has_carrier_permission') as mock_shipper:
                mock_carrier.return_value = False
                mock_shipper.return_value = False

                response = self.client.get(nested_url)
                self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

                # An anonymous user shouldn't have access to the shipment's transactions with an expired permission link
                response = self.client.get(f'{nested_url}?permission_link={invalid_permission_link.id}')
                self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

            # An anonymous user with a valid permission link should have access to the shipment's transactions
            response = self.client.get(f'{nested_url}?permission_link={valid_permission_link.id}')
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            data = response.json()['data']
            self.assertEqual(len(data), 2)
