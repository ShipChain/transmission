import json
from rest_framework import status
from rest_framework.reverse import reverse
from rest_framework.test import APITestCase, APIClient
from unittest import mock
from moto import mock_iot

from apps.shipments.models import Shipment
from apps.jobs.models import AsyncJob, Message, MessageType, JobState
from apps.shipments.rpc import Load110RPCClient
from apps.authentication import AuthenticatedUser

MESSAGE = [
    {'type': 'message'}
]

RPC_PARAMS = {
    "rpc_class": "rpc_class",
    "rpc_method": "rpc_method",
    "rpc_parameters": "rpc_parameters",
    "signing_wallet_id": "signing_wallet_id"
}

TRANSACTION_BODY = {
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
    "transactionHash": 'TxHash',
    "transactionIndex": 0
}

VAULT_ID = 'b715a8ff-9299-4c87-96de-a4b0a4a54509'
CARRIER_WALLET_ID = '3716ff65-3d03-4b65-9fd5-43d15380cff9'
SHIPPER_WALLET_ID = '48381c16-432b-493f-9f8b-54e88a84ec0a'
STORAGE_CRED_ID = '77b72202-5bcd-49f4-9860-bc4ec4fee07b'


class JobsAPITests(APITestCase):
    """
    Ensure serializer/model correctly validate, set, and generate the appropriate fields
    """

    def setUp(self):
        self.client = APIClient()

        self.user_1 = AuthenticatedUser({
            'user_id': '5e8f1d76-162d-4f21-9b71-2ca97306ef7b',
            'username': 'user1@shipchain.io',
            'email': 'user1@shipchain.io',
        })

        self.create_shipment()

    def set_user(self, user, token=None):
        self.client.force_authenticate(user=user, token=token)

    def create_message(self):
        if not self.async_jobs:
            self.create_async_jobs(self.shipments[0])

        self.messages = []

        self.messages.append(Message.objects.create(type=MessageType.ETH_TRANSACTION,
                                                    async_job=self.async_jobs[0].id))

        self.messages.append(Message.objects.create(type=MessageType.ERROR,
                                                    async_job=self.async_jobs[0].id))

    def create_async_jobs(self, shipment):
        self.async_jobs = []

        self.async_jobs.append(AsyncJob.objects.create(state=JobState.PENDING,
                                                       parameters=RPC_PARAMS,
                                                       wallet_lock_token='wallet_lock_token'))

        self.async_jobs.append(AsyncJob.objects.create(state=JobState.PENDING,
                                                       parameters=RPC_PARAMS,
                                                       wallet_lock_token='wallet_lock_token'))

        self.async_jobs.append(AsyncJob.objects.create(state=JobState.FAILED,
                                                       parameters=RPC_PARAMS,
                                                       wallet_lock_token='wallet_lock_token'))

        self.async_jobs.append(AsyncJob.objects.create(state=JobState.COMPLETE,
                                                       parameters=RPC_PARAMS,
                                                       wallet_lock_token='wallet_lock_token'))
        for job in self.async_jobs:
            job.joblistener_set.create(listener=shipment)

    def create_shipment(self):
        from apps.rpc_client import requests
        from tests.utils import mocked_rpc_response

        mock_shipment_rpc = Load110RPCClient

        mock_shipment_rpc.create_vault = mock.Mock(return_value=VAULT_ID)

        with mock.patch.object(requests.Session, 'post') as mock_method:
            mock_method.return_value = mocked_rpc_response({
                "vault_id": VAULT_ID
            })
            mock_method.return_value = mocked_rpc_response({
                "success": True,
                "vault_signed": {'hash': "TEST_VAULT_SIGNATURE"}
            })

            self.shipments = []
            self.load_shipments = []

            self.shipments.append(Shipment.objects.create(vault_id=VAULT_ID,
                                                          owner_id=self.user_1.id,
                                                          carrier_wallet_id=CARRIER_WALLET_ID,
                                                          shipper_wallet_id=SHIPPER_WALLET_ID,
                                                          storage_credentials_id=STORAGE_CRED_ID))

            self.load_shipments.append(self.shipments[0].loadshipmenttxm)

    def test_jobs_populated(self):
        """
        Test listing jobs responds with correct amount
        """
        self.create_async_jobs(self.shipments[0])
        url = reverse('job-list', kwargs={'version': 'v1'})

        self.set_user(self.user_1)
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        response_data = response.json()['data']

        self.assertEqual(len(response_data), len(self.async_jobs) + len(self.shipments))

    def test_jobs_detail(self):
        """
        Test calling a specific job only returns one object
        """
        self.create_async_jobs(self.shipments[0])
        url = reverse('job-detail', kwargs={'version': 'v1', 'pk': self.async_jobs[0].id})

        self.set_user(self.user_1)
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        response_data = response.json()

        # No devices created should return empty array
        self.assertEqual(len(response_data), 1)

    @mock_iot
    def test_add_jobs_message_error(self):
        """
        Test calling a specific job only returns one object
        """
        self.create_async_jobs(self.shipments[0])
        url = reverse('job-message', kwargs={'version': 'v1', 'pk': self.async_jobs[1].id})

        error_message = {"type": "ERROR", "body": {"exception": "Test Exception"}}

        response = self.client.post(url, json.dumps(error_message), content_type="application/json", X_NGINX_SOURCE='internal', X_SSL_CLIENT_VERIFY='SUCCESS', X_SSL_CLIENT_DN='/CN=engine.test-internal')
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        async_job = AsyncJob.objects.get(pk=self.async_jobs[1].id)
        self.assertEqual(async_job.state, JobState.FAILED)


    @mock_iot
    def test_add_jobs_message_success(self):
        """
        Test calling a specific job only returns one object
        """
        success_message = {"type": "ETH_TRANSACTION", "body": TRANSACTION_BODY}

        async_job = self.shipments[0].asyncjob_set.all()[:1].get()
        url = reverse('job-message', kwargs={'version': 'v1', 'pk': async_job.id})

        response = self.client.post(url, json.dumps(success_message), content_type="application/json", X_NGINX_SOURCE='internal', X_SSL_CLIENT_VERIFY='SUCCESS', X_SSL_CLIENT_DN='/CN=engine.test-internal')
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        async_job = AsyncJob.objects.get(pk=async_job.id)
        self.assertEqual(async_job.state, JobState.COMPLETE)
