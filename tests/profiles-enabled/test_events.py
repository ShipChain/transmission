"""
Copyright 2018 ShipChain, Inc.

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""
import pytest
from django.urls import reverse
from mock import patch
from rest_framework import status
from shipchain_common.test_utils import AssertionHelper

from apps.eth.models import Event, EthAction


@pytest.fixture(scope='session')
def contract_event():
    return {
        "address": "0x25Ff5dc79A7c4e34254ff0f4a19d69E491201DD3",
        "blockNumber": 3,
        "transactionHash": "0xc18a24a35052a5a3375ee6c2c5ddd6b0587cfa950b59468b67f63f284e2cc382",
        "transactionIndex": 0,
        "blockHash": "0x62469a8d113b27180c139d88a25f0348bb4939600011d33382b98e10842c85d9",
        "logIndex": 0,
        "removed": False,
        "id": "log_25652065",
        "returnValues": {
            "0": "0xFCaf25bF38E7C86612a25ff18CB8e09aB07c9885",
            "shipTokenContractAddress": "0xFCaf25bF38E7C86612a25ff18CB8e09aB07c9885"
        },
        "event": "SetTokenContractAddressEvent",
        "signature": "0xbbbf32f08c8c0621e580dcf0a8e0024525ec357db61bb4faa1a639d4f958a824",
        "raw": {
            "data": "0x000000000000000000000000fcaf25bf38e7c86612a25ff18cb8e09ab07c9885",
            "topics": [
                "0xbbbf32f08c8c0621e580dcf0a8e0024525ec357db61bb4faa1a639d4f958a824"
            ]
        }
    }


@pytest.fixture(scope='session')
def token_event():
    return {
        "address": "0x25Ff5dc79A7c4e34254ff0f4a19d69E491201DD3",
        "blockNumber": 3,
        "transactionHash": "0xc18a24a35052a5a3375ee6c2c5ddd6b0587cfa950b59468b67f63f284e2cc382",
        "transactionIndex": 0,
        "blockHash": "0x62469a8d113b27180c139d88a25f0348bb4939600011d33382b98e10842c85d9",
        "logIndex": 0,
        "removed": False,
        "id": "log_25652065",
        "returnValues": {
            "from": "0xFCaf25bF38E7C86612a25ff18CB8e09aB07c9885",
            "to": "0xFCaf25bF38E7C86612a25ff18CB8e09aB07c9885",
            "value": 10000000000000000000000
        },
        "event": "Transfer",
        "signature": "0xbbbf32f08c8c0621e580dcf0a8e0024525ec357db61bb4faa1a639d4f958a824",
        "raw": {
            "data": "0x000000000000000000000000fcaf25bf38e7c86612a25ff18cb8e09ab07c9885",
            "topics": [
                "0xbbbf32f08c8c0621e580dcf0a8e0024525ec357db61bb4faa1a639d4f958a824"
            ]
        }
    }


@pytest.fixture()
def mock_event_signal(mocker):
    from apps.eth.signals import event_update
    mocker.patch.object(event_update, 'send')


@pytest.mark.django_db
def test_event_update(client_alice, shipment, contract_event, mock_event_signal):
    url = reverse('event-list', kwargs={'version': 'v1'})
    # Create EthAction so events don't get ignored
    EthAction.objects.create(transaction_hash=contract_event['transactionHash'],
                             async_job_id=shipment.asyncjob_set.first().id,
                             shipment=shipment)

    data = {
        'events': contract_event,
        'project': 'LOAD'
    }

    data_batched = {
        'events': [contract_event, contract_event],
        'project': 'LOAD'
    }

    response = client_alice.post(url, data)
    assert response.status_code == status.HTTP_403_FORBIDDEN

    # Set NGINX headers for engine auth
    response = client_alice.post(url, data, X_NGINX_SOURCE='internal', X_SSL_CLIENT_VERIFY='SUCCESS',
                                 X_SSL_CLIENT_DN='/CN=engine.test-internal')
    AssertionHelper.HTTP_204(response)

    # Test idempotency of Events
    num_events = Event.objects.count()
    response = client_alice.post(url, data, X_NGINX_SOURCE='internal', X_SSL_CLIENT_VERIFY='SUCCESS',
                                 X_SSL_CLIENT_DN='/CN=engine.test-internal')
    AssertionHelper.HTTP_204(response)
    assert Event.objects.count() == num_events

    response = client_alice.post(url, data_batched, X_NGINX_SOURCE='internal', X_SSL_CLIENT_VERIFY='SUCCESS',
                                 X_SSL_CLIENT_DN='/CN=engine.test-internal')
    AssertionHelper.HTTP_204(response)
    assert Event.objects.count() == num_events

    # Events should be idempotent by transactionHash and logIndex
    data['events']['blockNumber'] = 9999
    response = client_alice.post(url, data, X_NGINX_SOURCE='internal', X_SSL_CLIENT_VERIFY='SUCCESS',
                                 X_SSL_CLIENT_DN='/CN=engine.test-internal')
    AssertionHelper.HTTP_204(response)
    assert Event.objects.count() == num_events

    data['events']['logIndex'] = 1
    response = client_alice.post(url, data, X_NGINX_SOURCE='internal', X_SSL_CLIENT_VERIFY='SUCCESS',
                                 X_SSL_CLIENT_DN='/CN=engine.test-internal')
    AssertionHelper.HTTP_204(response)
    assert Event.objects.count() == (num_events + 1)


@pytest.mark.django_db
def test_event_transfer(client_alice, token_event):
    url = reverse('event-list', kwargs={'version': 'v1'})
    data = {
        'events': token_event,
        'project': 'ShipToken'
    }
    response = client_alice.post(url, data)
    assert response.status_code == status.HTTP_403_FORBIDDEN

    with patch('apps.eth.views.log_metric') as mocked:
        # Set NGINX headers for engine auth
        response = client_alice.post(url, data, X_NGINX_SOURCE='internal', X_SSL_CLIENT_VERIFY='SUCCESS',
                                     X_SSL_CLIENT_DN='/CN=engine.test-internal')
        AssertionHelper.HTTP_204(response)

        assert mocked.call_count == 2
