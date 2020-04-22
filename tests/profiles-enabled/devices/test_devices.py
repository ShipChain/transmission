#  Copyright 2020 ShipChain, Inc.
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.
import json
from datetime import datetime, timedelta
from datetime import timezone

import pytest
from django.urls import reverse
from shipchain_common.test_utils import AssertionHelper
from rest_framework import status
from django.conf import settings


@pytest.fixture
def mocked_sensors_success(mock_successful_wallet_owner_calls, device):
    mock_successful_wallet_owner_calls.register_uri(
        mock_successful_wallet_owner_calls.GET,
        f'{settings.PROFILES_URL}/api/v1/device/{device.id}/sensor',
        body=json.dumps({"links": {
            "first": f"{settings.PROFILES_URL}/api/v1/device/",
            "last": f"{settings.PROFILES_URL}/api/v1/device/",
            "next": None,
        }, "data": [{}]}),
        status=status.HTTP_200_OK)
    return mock_successful_wallet_owner_calls


@pytest.fixture
def mocked_sensors_fail(mock_successful_wallet_owner_calls, device):
    mock_successful_wallet_owner_calls.register_uri(mock_successful_wallet_owner_calls.GET,
                                                    f'{settings.PROFILES_URL}/api/v1/device/{device.id}/sensor',
                                                    body=json.dumps({'errors': [{'detail': '404 error'}]}),
                                                    status=status.HTTP_404_NOT_FOUND)
    return mock_successful_wallet_owner_calls


@pytest.fixture
def mocked_sensors_non_json(mock_successful_wallet_owner_calls, device):
    mock_successful_wallet_owner_calls.register_uri(mock_successful_wallet_owner_calls.GET,
                                                    f'{settings.PROFILES_URL}/api/v1/device/{device.id}/sensor',
                                                    body=str(datetime.now()),
                                                    status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    return mock_successful_wallet_owner_calls


class TestSensorsWithShipmentList:
    @pytest.fixture(autouse=True)
    def set_up(self, device, shipment_alice_with_device):
        self.device = device
        self.shipment_alice_with_device = shipment_alice_with_device
        self.url = reverse('device-sensor', kwargs={'version': 'v1', 'device_pk': device.id})

    def test_unauthenticated_user_fails(self, api_client):
        response = api_client.get(self.url)
        AssertionHelper.HTTP_403(response, vnd=False, error='You do not have permission to perform this action.')

    def test_shipment_owner_succeeds(self, client_alice, mocked_sensors_success):
        response = client_alice.get(self.url)
        AssertionHelper.HTTP_200(response, is_list=True)
        mocked_sensors_success.assert_calls([{
                'path': f'/api/v1/device/{self.device.id}/sensor',
                'body': None,
                'host': settings.PROFILES_URL.replace('http://', ''),
            }])

    def test_wallet_owner_succeeds(self, client_bob, mocked_sensors_success,
                                   successful_wallet_owner_calls_assertions):
        response = client_bob.get(self.url)
        AssertionHelper.HTTP_200(response, is_list=True)
        successful_wallet_owner_calls_assertions.append({
                'path': f'/api/v1/device/{self.device.id}/sensor',
                'body': None,
                'host': settings.PROFILES_URL.replace('http://', ''),
            })
        mocked_sensors_success.assert_calls(successful_wallet_owner_calls_assertions)

    def test_non_wallet_owner_fails(self, client_bob, nonsuccessful_wallet_owner_calls_assertions,
                                    mock_non_wallet_owner_calls):
        response = client_bob.get(self.url)
        AssertionHelper.HTTP_403(response, vnd=False, error='You do not have permission to perform this action.')
        mock_non_wallet_owner_calls.assert_calls(nonsuccessful_wallet_owner_calls_assertions)

    def test_expired_permission_link_fails(self, api_client, permission_link_device_shipment_expired,
                                           mock_non_wallet_owner_calls, nonsuccessful_wallet_owner_calls_assertions):
        response = api_client.get(f'{self.url}?permission_link={permission_link_device_shipment_expired.id}')
        AssertionHelper.HTTP_403(response, vnd=False, error='You do not have permission to perform this action.')
        mock_non_wallet_owner_calls.assert_calls(nonsuccessful_wallet_owner_calls_assertions)

    def test_permission_link_succeeds(self, api_client, mocked_sensors_success, permission_link_device_shipment):
        response = api_client.get(f'{self.url}?permission_link={permission_link_device_shipment.id}')
        AssertionHelper.HTTP_200(response, is_list=True)
        mocked_sensors_success.assert_calls([{
                'path': f'/api/v1/device/{self.device.id}/sensor',
                'body': None,
                'host': settings.PROFILES_URL.replace('http://', ''),
            }])

    def test_fails_pass_through(self, client_alice, mocked_sensors_fail):
        response = client_alice.get(self.url)
        AssertionHelper.HTTP_404(response, error='404 error')
        mocked_sensors_fail.assert_calls([{
                'path': f'/api/v1/device/{self.device.id}/sensor',
                'body': None,
                'host': settings.PROFILES_URL.replace('http://', ''),
            }])

    def test_queries_pass_through(self, client_alice, mocked_sensors_success):
        response = client_alice.get(f'{self.url}?search=field')
        AssertionHelper.HTTP_200(response, is_list=True)
        mocked_sensors_success.assert_calls([{
                'path': f'/api/v1/device/{self.device.id}/sensor',
                'body': None,
                'host': settings.PROFILES_URL.replace('http://', ''),
                'query': {'search': 'field'}
            }])

    def test_non_json_fails(self, client_alice, mocked_sensors_non_json):
        response = client_alice.get(self.url)
        # AssertionHelper.HTTP_503(response, vnd=False, error='Invalid response returned from profiles.')
        assert response.status_code == 503
        assert response.json()['detail'] == 'Invalid response returned from profiles.'
        mocked_sensors_non_json.assert_calls([{
                'path': f'/api/v1/device/{self.device.id}/sensor',
                'body': None,
                'host': settings.PROFILES_URL.replace('http://', ''),
            }])
