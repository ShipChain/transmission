from rest_framework.test import APITestCase
from apps.eth.models import TransactionReceipt, EthAction
from apps.jobs.models import AsyncJob
from django.db import models
from rest_framework import status
from rest_framework.reverse import reverse


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
    def createAsyncJobs(self):
        self.asyncJobs = []
        self.asyncJobs.append(AsyncJob.objects.create())

    def createEthAction(self, listener):
        self.ethActions = []
        self.ethActions.append(EthAction.objects.create(transaction_hash=TRANSACTION_HASH, async_job=self.asyncJobs[0]))
        self.ethActions.append(EthAction.objects.create(transaction_hash=TRANSACTION_HASH_2,
                                                        async_job=self.asyncJobs[0]))

        self.ethActions[0].ethlistener_set.create(listener=listener)
        self.ethActions[0].save()

        self.ethActions[1].ethlistener_set.create(listener=listener)
        self.ethActions[1].save()

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
        class DummyEthListener(models.Model):
            id = models.CharField(primary_key=True, max_length=36)
            owner_id = models.CharField(null=False, max_length=36)

            class Meta:
                app_label = 'apps.jobs'

        listener = DummyEthListener(id='FAKE_LISTENER_ID', owner_id=USER_ID)

        self.createAsyncJobs()
        self.createEthAction(listener)
        self.createTransactionReceipts()

        url = reverse('transaction-detail', kwargs={'pk': TRANSACTION_HASH, 'version': 'v1'})

        response = self.client.get(url)
        response_json = response.json()
        print(response.content)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response_json['included'][1]['attributes']['from_address'], FROM_ADDRESS)

    def test_transaction_list(self):
        class DummyEthListener(models.Model):
            id = models.CharField(primary_key=True, max_length=36)
            owner_id = models.CharField(null=False, max_length=36)

            class Meta:
                app_label = 'apps.jobs'

        listener = DummyEthListener(id='FAKE_LISTENER_ID_2', owner_id=USER_ID)

        self.createAsyncJobs()
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
