import copy
from unittest import mock

import requests
import boto3
import json
from geocoder.keys import mapbox_access_token
from rest_framework import status
from rest_framework.reverse import reverse
from rest_framework.test import APITestCase, APIClient
from jose import jws
from moto import mock_iot
import httpretty
import json
import os
import re
from unittest.mock import patch

from apps.jobs.models import AsyncJob, Message, MessageType, JobListener, JobState
from apps.rpc_client import RPCClient
from django.contrib.gis.geos import Point
from apps.utils import AuthenticatedUser, random_id
from tests.utils import replace_variables_in_string, create_form_content

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

    def set_user(self, user, token=None):
        self.client.force_authenticate(user=user, token=token)

    def create_message(self):
        if not self.async_jobs:
            self.create_async_jobs()

        self.messages = []

        self.messages.append(Message.objects.create(type=MessageType.ETH_TRANSACTION,
                                                    async_job=self.async_jobs[0].id))

        self.messages.append(Message.objects.create(type=MessageType.ERROR,
                                                    async_job=self.async_jobs[0].id))

    def create_async_jobs(self):
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

    def test_jobs_empty(self):
        """
        Test listing jobs requires authentication
        """
        url = reverse('job-list', kwargs={'version': 'v1'})

        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        response_data = response.json()

        # No devices created should return empty array
        self.assertEqual(len(response_data['data']), 0)

    def test_jobs_populated(self):
        """
        Test listing jobs responds with correct amount
        """
        self.create_async_jobs()
        url = reverse('job-list', kwargs={'version': 'v1'})

        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        response_data = response.json()['data']

        self.assertEqual(len(response_data), 4)

    def test_jobs_detail(self):
        """
        Test calling a specific job only returns one object
        """
        self.create_async_jobs()
        url = reverse('job-detail', kwargs={'version': 'v1', 'pk': self.async_jobs[0].id})

        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        response_data = response.json()

        # No devices created should return empty array
        self.assertEqual(len(response_data), 1)

    def test_add_jobs_message(self):
        """
        Test calling a specific job only returns one object
        """
        self.create_async_jobs()
        url = reverse('job-message', kwargs={'version': 'v1', 'pk': self.async_jobs[1].id})

        mock_rpc_client = RPCClient

        mock_rpc_client.send_transaction = mock.Mock(return_value={
            "type": "ETH_TRANSACTION",
            "body": TRANSACTION_BODY
        })
        mock_rpc_client.sign_transaction = mock.Mock(return_value={
            "type": "ETH_TRANSACTION",
            "body": TRANSACTION_BODY
        })

        message = {"type": "ERROR", "body": {"exception": "Test Exception"}}

        response = self.client.post(url, json.dumps(message), content_type="application/json")
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        async_job = AsyncJob.objects.get(pk=self.async_jobs[1].id)
        self.assertEqual(async_job.state, JobState.FAILED)
