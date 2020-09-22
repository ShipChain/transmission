import datetime
from unittest import mock

from django.conf import settings as test_settings
from rest_framework import status
from rest_framework.reverse import reverse
from rest_framework.test import APIClient
from apps.eth.models import TransactionReceipt, EthAction
from apps.jobs.models import AsyncJob
from apps.shipments.models import PermissionLink


from tests.conftest import BLOCK_HASH, TRANSACTION_HASH, CUMULATIVE_GAS_USED, BLOCK_NUMBER, FROM_ADDRESS, GAS_USED, LOGS, LOGS_BLOOM, STATUS, TO_ADDRESS
FROM_ADDRESS_2 = FROM_ADDRESS[-1] + 'f'


class TestTransactionReceipts:
    def createAsyncJobs(self, shipment):
        self.asyncJobs = []
        self.asyncJobs.append(AsyncJob.objects.create(shipment=shipment))

    def createEthAction(self, listener):
        self.ethActions = []
        self.ethActions.append(EthAction.objects.create(transaction_hash=TRANSACTION_HASH, async_job=self.asyncJobs[0],
                                                        shipment=listener))
        self.ethActions.append(EthAction.objects.create(transaction_hash=TRANSACTION_HASH + '2',
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

    def test_transaction_get(self, client_alice, shipment_alice):
        self.createAsyncJobs(shipment_alice)
        self.createEthAction(shipment_alice)
        self.createTransactionReceipts()

        url = reverse('transaction-detail', kwargs={'pk': TRANSACTION_HASH, 'version': 'v1'})
        response = client_alice.get(url)
        response_json = response.json()

        assert response.status_code == status.HTTP_200_OK
        assert response_json['included'][1]['attributes']['from_address'] == FROM_ADDRESS

    def test_transaction_list(self, client_alice, shipment_alice, profiles_ids, mocked_profiles, modified_http_pretty):

        valid_permission_link = PermissionLink.objects.create(
            expiration_date=datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=1),
            shipment=shipment_alice
        )

        invalid_permission_link = PermissionLink.objects.create(
            expiration_date=datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=-1),
            shipment=shipment_alice
        )

        self.createAsyncJobs(shipment_alice)
        self.createEthAction(shipment_alice)
        self.createTransactionReceipts()

        # Ensure two different transaction receipts were created
        assert TransactionReceipt.objects.count() == 2

        url = reverse('transaction-list', kwargs={'version': 'v1'})

        # Request without wallet_address query field should fail
        response = client_alice.get(url)
        assert response.status_code == status.HTTP_400_BAD_REQUEST

        # request for specific eth actions using wallet_address should fail
        response = client_alice.get(f'{url}?wallet_address={FROM_ADDRESS}')
        assert response.status_code == status.HTTP_400_BAD_REQUEST

        # request for specific eth actions should only return ones with that from_address
        response = client_alice.get(f'{url}?wallet_id={profiles_ids["shipper_wallet_id"]}')
        response_json = response.json()
        assert response.status_code == status.HTTP_200_OK
        assert len(response_json['data']) == 1

        modified_http_pretty.register_uri('GET',
                                          f"{test_settings.PROFILES_URL}/api/v1/wallet/{profiles_ids['shipper_wallet_id']}/",
                                          status=status.HTTP_401_UNAUTHORIZED)

        # request for specific eth actions should fail if the profiles request fails
        response = client_alice.get(f'{url}?wallet_id={profiles_ids["shipper_wallet_id"]}')
        assert response.status_code == status.HTTP_400_BAD_REQUEST

        # Shipment transactions list
        nested_url = reverse('shipment-transactions-list', kwargs={'version': 'v1', 'shipment_pk': shipment_alice.id})
        response = client_alice.get(nested_url)
        assert response.status_code == status.HTTP_200_OK

        # Ordering works as expected
        response = client_alice.get(f'{nested_url}?ordering=-created_at')
        assert response.status_code == status.HTTP_200_OK
        response_json = response.json()
        assert response_json['data'][0]['attributes']['transaction_hash'] == TRANSACTION_HASH + '2'

        # A Transactions list view cannot be accessed by an anonymous user on a nested route
        anon_client = APIClient()
        anon_client.force_authenticate(None, None)

        with mock.patch('apps.permissions.IsShipperMixin.has_shipper_permission') as mock_carrier, \
                mock.patch('apps.permissions.IsCarrierMixin.has_carrier_permission') as mock_shipper:
            mock_carrier.return_value = False
            mock_shipper.return_value = False

            response = anon_client.get(nested_url)
            assert response.status_code == status.HTTP_403_FORBIDDEN

            # An anonymous user shouldn't have access to the shipment's transactions with an expired permission link
            response = anon_client.get(f'{nested_url}?permission_link={invalid_permission_link.id}')
            assert response.status_code == status.HTTP_403_FORBIDDEN

        # An anonymous user with a valid permission link should have access to the shipment's transactions
        response = anon_client.get(f'{nested_url}?permission_link={valid_permission_link.id}')
        assert response.status_code == status.HTTP_200_OK
        data = response.json()['data']
        assert len(data) == 2
