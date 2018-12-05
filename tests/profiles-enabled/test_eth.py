from apps.eth.models import TransactionReceipt, EthAction
from apps.jobs.models import AsyncJob
from django.db import models
from rest_framework import status
from rest_framework.reverse import reverse
from rest_framework.test import APITestCase, APIClient, force_authenticate
from apps.authentication import AuthenticatedUser
from conf import test_settings
import httpretty
import json
import jwt


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

private_key = b"""-----BEGIN RSA PRIVATE KEY-----
MIICXgIBAAKBgQDtAMh97vXP8KnZUEUrnUT8nz0+8oLrOfBB19+eLIDfNvACNA2D
swOK9gCY+/QcOCR+c5yGTe8lCNwlwW42ingABeM5PigYZ1AfNHVPatcLzO9u3dZG
WMsAB6Un9xmaJfIuKv85jX7Wu9Pkq7EaZbr8pbbMNcYiX1amCrXggZDWOQIDAQAB
AoGBAINMQsZZov5+8mm86YUfDH/zbAe6bEMKhwrDIFRNjVub4N0nnzEN9HGAlZYr
RvJ3O+h9/gH9nPXkcanM/lTi41T27Vn2TZ9Fp71BwOVgnaisjwtY01AIASTl8gWA
rwleIhGY3Kbw6D7V5lqyr8UWsi20SBc9+EILF+ugpUZoXbWtAkEA/GikOeojxPJa
L3MPD+Bc6pz570VpYYtkDUHH9gJgVSb/xohNWoA4zT71rxjD0yjA06mhgxWqg3PP
WAZ9276gkwJBAPBgB2SaibmtP7efiWZfMNUGo2J6t47g7B5wv2C/YmSO2twlaik6
SL2wXVzLnU/Phmjb+bbjYE5hVASlenRSiYMCQGl1dxhTgXpqH9AvbJ2finLj/3E/
ORZuXPFFCLz6pTEuyDM1A8zKQfFPWus7l6YEIvzMpRTV2pZtrrYCkFddwE0CQQCi
IHL8FQuts7/VLwKyjKPYGukaZCDoeqZnha5fJ9bKclwFviqTch9b6dee3irViOhk
U3JjO4tacmUD2UT1rjHXAkEAjpPF0Zdv4Dbf52MfeowoLw/KyreQfRVCIeSG9A4H
3xlhpEJUcgzUV1E2BJRitz2w6ItAFm9Lhx7EPO4ZPHPylQ==
-----END RSA PRIVATE KEY-----"""


class TransactionReceiptTestCase(APITestCase):
    def setUp(self):
        self.client = APIClient()

        self.user_1 = AuthenticatedUser({
            'user_id': USER_ID,
            'username': 'user1@shipchain.io',
            'email': 'user1@shipchain.io',
        })

    def set_user(self, user, token=None):
        self.client.force_authenticate(user=user, token=token)

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

    @httpretty.activate
    def test_transaction_list(self):
        class DummyEthListener(models.Model):
            id = models.CharField(primary_key=True, max_length=36)
            owner_id = models.CharField(null=False, max_length=36)

            class Meta:
                app_label = 'apps.jobs'

        listener = DummyEthListener(id='FAKE_LISTENER_ID', owner_id=USER_ID)

        self.createAsyncJobs()
        self.createEthAction(listener)
        self.createTransactionReceipts()

        token = jwt.encode({'email': 'a@domain.com', 'username': 'a@domain.com', 'aud': '11111'},
                           private_key, algorithm='RS256',
                           headers={'kid': '230498151c214b788dd97f22b85410a5', 'aud': '11111'})

        self.set_user(self.user_1, token=token)

        # Ensure two different transaction receipts were created
        self.assertEqual(TransactionReceipt.objects.count(), 2)

        url = reverse('transaction-list', kwargs={'version': 'v1'})

        # Request without wallet_address query field should fail
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        # request for specific eth actions using wallet_address should fail
        response = self.client.get(f'{url}?wallet_address={FROM_ADDRESS}')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        httpretty.register_uri(httpretty.GET,
                               f"{test_settings.PROFILES_URL}/api/v1/wallet/{WALLET_ID}/",
                               body=json.dumps({'data': {'attributes': {'address':  FROM_ADDRESS}}}),
                               status=status.HTTP_200_OK)

        # request for specific eth actions should only return ones with that from_address
        response = self.client.get(f'{url}?wallet_id={WALLET_ID}&shipper_wallet_id={WALLET_ID}')
        force_authenticate(response, user=self.user_1, token=token)
        print(response.content)
        response_json = response.json()
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response_json['data']), 1)

        httpretty.register_uri(httpretty.GET,
                               f"{test_settings.PROFILES_URL}/api/v1/wallet/{WALLET_ID}/",
                               status=status.HTTP_401_UNAUTHORIZED)

        # request for specific eth actions should fail if the profiles request fails
        response = self.client.get(f'{url}?wallet_id={WALLET_ID}')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
