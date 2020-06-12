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
from copy import deepcopy
from datetime import timedelta

import pytest
from django.urls import reverse
from moto import mock_iot
from rest_framework import status
from shipchain_common.test_utils import AssertionHelper
from shipchain_common.utils import random_id

from apps.shipments.models import TelemetryData
from apps.utils import Aggregates, TimeTrunc


def add_telemetry_data_to_shipment(telemetry_data, shipment):
    for telemetry in telemetry_data:
        TelemetryData.objects.create(shipment=shipment,
                                     device=shipment.device,
                                     **telemetry)


@mock_iot
class TestPostTelemetryData:
    @pytest.fixture(autouse=True)
    def set_up(self, shipment_alice_with_device, create_signed_telemetry_post):
        self.telemetry_url = reverse('device-telemetry',
                                     kwargs={'version': 'v1', 'pk': shipment_alice_with_device.device.id})
        self.random_telemetry_url = reverse('device-telemetry', kwargs={'version': 'v1', 'pk': random_id()})

    def test_unsigned_data_fails(self, api_client, create_unsigned_telemetry_post):
        response = api_client.post(self.telemetry_url, create_unsigned_telemetry_post)
        AssertionHelper.HTTP_400(response, error="This value does not match the required pattern.", pointer='payload')

    def test_signed_data_succeeds(self, api_client, create_signed_telemetry_post):
        response = api_client.post(self.telemetry_url, create_signed_telemetry_post)
        AssertionHelper.HTTP_204(response)
        assert TelemetryData.objects.all().count() == 1

    def test_invalid_signed_data_fails(self, api_client, invalid_post_signed_telemetry):
        response = api_client.post(self.telemetry_url, invalid_post_signed_telemetry)
        AssertionHelper.HTTP_400(response, error="This field is required.")

    def test_batch_signed_data_succeeds(self, api_client, create_batch_signed_telemetry_post):
        response = api_client.post(self.telemetry_url, create_batch_signed_telemetry_post)
        AssertionHelper.HTTP_204(response)
        assert TelemetryData.objects.all().count() == 2

    def test_nonextant_device_fails(self, api_client, create_signed_telemetry_post):
        response = api_client.post(self.random_telemetry_url, create_signed_telemetry_post)
        AssertionHelper.HTTP_403(response, error='No shipment/route found associated to device.')

    def test_no_get_calls(self, api_client):
        response = api_client.get(self.random_telemetry_url)
        AssertionHelper.HTTP_405(response)

    def test_no_patch_calls(self, api_client, create_signed_telemetry_post):
        response = api_client.patch(self.random_telemetry_url, create_signed_telemetry_post)
        AssertionHelper.HTTP_405(response)

    def test_no_del_calls(self, api_client):
        response = api_client.delete(self.random_telemetry_url)
        AssertionHelper.HTTP_405(response)


class TestRetrieveTelemetryData:
    @pytest.fixture(autouse=True)
    def set_up(self, shipment_alice_with_device, create_signed_telemetry_post, shipment_alice, unsigned_telemetry,
               successful_wallet_owner_calls_assertions, nonsuccessful_wallet_owner_calls_assertions):
        self.telemetry_url = reverse('shipment-telemetry-list', kwargs={'version': 'v1', 'shipment_pk': shipment_alice_with_device.id})
        self.empty_telemetry_url = reverse('shipment-telemetry-list', kwargs={'version': 'v1', 'shipment_pk': shipment_alice.id})
        self.random_telemetry_url = reverse('shipment-telemetry-list', kwargs={'version': 'v1', 'shipment_pk': random_id()})
        self.shipment_alice_with_device = shipment_alice_with_device
        add_telemetry_data_to_shipment([unsigned_telemetry], self.shipment_alice_with_device)
        self.unsigned_telemetry = unsigned_telemetry
        self.assert_success = successful_wallet_owner_calls_assertions
        self.assert_fail = nonsuccessful_wallet_owner_calls_assertions

    def test_unauthenticated_user_fails(self, api_client, mock_non_wallet_owner_calls):
        response = api_client.get(self.telemetry_url)
        AssertionHelper.HTTP_403(response, vnd=False)

    def test_random_shipment_url_fails(self, client_alice):
        response = client_alice.get(self.random_telemetry_url)
        AssertionHelper.HTTP_403(response, vnd=False)

    def test_wallet_owner_retrieves(self, client_bob, mock_successful_wallet_owner_calls):
        response = client_bob.get(self.telemetry_url)
        self.unsigned_telemetry.pop('version')
        AssertionHelper.HTTP_200(response, is_list=True, vnd=False, attributes=self.unsigned_telemetry)
        assert len(response.json()) == 1
        mock_successful_wallet_owner_calls.assert_calls(self.assert_success)

    def test_non_wallet_owner_fails(self, client_bob, mock_non_wallet_owner_calls):
        response = client_bob.get(self.telemetry_url)
        AssertionHelper.HTTP_403(response, vnd=False)
        mock_non_wallet_owner_calls.assert_calls(self.assert_fail)

    def test_shipment_owner_retrieves(self, client_alice):
        response = client_alice.get(self.telemetry_url)
        self.unsigned_telemetry.pop('version')
        AssertionHelper.HTTP_200(response, is_list=True, vnd=False, attributes=self.unsigned_telemetry)

    def test_filter_sensor(self, client_alice, unsigned_telemetry_different_sensor):
        add_telemetry_data_to_shipment([unsigned_telemetry_different_sensor],
                                       self.shipment_alice_with_device)
        response = client_alice.get(f'{self.telemetry_url}?sensor_id={self.unsigned_telemetry["sensor_id"]}')
        self.unsigned_telemetry.pop('version')
        AssertionHelper.HTTP_200(response, is_list=True, vnd=False, attributes=self.unsigned_telemetry)
        assert len(response.json()) == 1
        assert self.unsigned_telemetry['sensor_id'] != unsigned_telemetry_different_sensor['sensor_id']

    def test_filter_hardware_id(self, client_alice, unsigned_telemetry_different_hardware):
        add_telemetry_data_to_shipment([unsigned_telemetry_different_hardware],
                                       self.shipment_alice_with_device)
        response = client_alice.get(f'{self.telemetry_url}?hardware_id={self.unsigned_telemetry["hardware_id"]}')
        self.unsigned_telemetry.pop('version')
        AssertionHelper.HTTP_200(response, is_list=True, vnd=False, attributes=self.unsigned_telemetry)
        assert self.unsigned_telemetry['hardware_id'] != unsigned_telemetry_different_hardware['hardware_id']
        assert len(response.json()) == 1

    def test_timestamp(self, client_alice, unsigned_telemetry_different_hardware, current_datetime):
        telemetry_copy = deepcopy(self.unsigned_telemetry)
        telemetry_copy['timestamp'] = (current_datetime + timedelta(days=1)).isoformat().replace('+00:00', 'Z')
        add_telemetry_data_to_shipment([telemetry_copy], self.shipment_alice_with_device)

        valid_timestamp = (current_datetime + timedelta(hours=12)).isoformat().replace('+00:00', 'Z')
        invalid_before_timestamp = (current_datetime + timedelta(hours=18)).isoformat().replace('+00:00', 'Z')
        invalid_after_timestamp = (current_datetime + timedelta(hours=6)).isoformat().replace('+00:00', 'Z')

        response = client_alice.get(f'{self.telemetry_url}?before=NOT A TIMESTAMP')
        AssertionHelper.HTTP_400(response)
        assert response.json()['before'] == ['Enter a valid date/time.']

        response = client_alice.get(f'{self.telemetry_url}?before={valid_timestamp}')
        self.unsigned_telemetry.pop('version')
        AssertionHelper.HTTP_200(response, is_list=True, vnd=False, attributes=self.unsigned_telemetry, count=1)

        response = client_alice.get(f'{self.telemetry_url}?after={valid_timestamp}')
        telemetry_copy.pop('version')
        AssertionHelper.HTTP_200(response, is_list=True, vnd=False, attributes=telemetry_copy, count=1)

        response = client_alice.get(f'{self.telemetry_url}?before={valid_timestamp}&after={invalid_after_timestamp}')
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.json()[0] == \
            f'Invalid timemismatch applied. Before timestamp {valid_timestamp} is greater than after: {invalid_after_timestamp}'

        response = client_alice.get(f'{self.telemetry_url}?after={valid_timestamp}&before={invalid_before_timestamp}')
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.json()[0] == \
            f'Invalid timemismatch applied. Before timestamp {invalid_before_timestamp} is greater than after: {valid_timestamp}'

    def test_aggregate_requirements(self, client_alice):
        response = client_alice.get(f'{self.telemetry_url}?aggregate=NOT_AN_AGGREGATE')
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.json()[0] == f'Invalid aggregate supplied should be in: {list(Aggregates.__members__.keys())}'

        response = client_alice.get(f'{self.telemetry_url}?aggregate={Aggregates.average.name}')
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.json()[0] == \
               f'No time selector supplied with aggregation. Should be in {list(TimeTrunc.__members__.keys())}'

        response = client_alice.get(f'{self.telemetry_url}?per={TimeTrunc.minutes.name}')
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.json()[0] == \
               f'No aggregator supplied with time selector. Should be in {list(Aggregates.__members__.keys())}'

    def test_aggregate_success(self, client_alice, unsigned_telemetry_different_sensor):
        response = client_alice.get(
            f'{self.telemetry_url}?aggregate={Aggregates.average.name}&per={TimeTrunc.minutes.name}')
        AssertionHelper.HTTP_200(response, is_list=True, vnd=False, attributes={
            'value': self.unsigned_telemetry['value']
        })
        assert len(response.json()) == 1

        self.unsigned_telemetry['value'] = 20
        add_telemetry_data_to_shipment([self.unsigned_telemetry],
                                       self.shipment_alice_with_device)
        response = client_alice.get(
            f'{self.telemetry_url}?aggregate={Aggregates.average.name}&per={TimeTrunc.minutes.name}')
        self.unsigned_telemetry['value'] = 15
        AssertionHelper.HTTP_200(response, is_list=True, vnd=False, attributes={
            'value': self.unsigned_telemetry['value']
        })
        assert len(response.json()) == 1

        response = client_alice.get(
            f'{self.telemetry_url}?aggregate={Aggregates.minimum.name}&per={TimeTrunc.minutes.name}')
        AssertionHelper.HTTP_200(response, is_list=True, vnd=False, attributes={
            'value': 10
        })
        assert len(response.json()) == 1
        response = client_alice.get(
            f'{self.telemetry_url}?aggregate={Aggregates.maximum.name}&per={TimeTrunc.minutes.name}')
        self.unsigned_telemetry['value'] = 20
        AssertionHelper.HTTP_200(response, is_list=True, vnd=False, attributes={
            'value': self.unsigned_telemetry['value']
        })
        assert len(response.json()) == 1

    def test_permission_link_succeeds(self, api_client, permission_link_device_shipment):
        response = api_client.get(f'{self.telemetry_url}?permission_link={permission_link_device_shipment.id}')
        self.unsigned_telemetry.pop('version')
        AssertionHelper.HTTP_200(response, is_list=True, vnd=False, attributes=self.unsigned_telemetry)
        assert self.unsigned_telemetry in response.json()
        assert len(response.json()) == 1

    def test_permission_link_fail(self, api_client, permission_link_device_shipment_expired):
        response = api_client.get(f'{self.telemetry_url}?permission_link={permission_link_device_shipment_expired.id}')
        AssertionHelper.HTTP_403(response, vnd=False)

    def test_unique_per_shipment(self, client_alice):
        response = client_alice.get(self.empty_telemetry_url)
        assert response.status_code == status.HTTP_200_OK
        assert len(response.json()) == 0
        assert TelemetryData.objects.all().count() == 1
