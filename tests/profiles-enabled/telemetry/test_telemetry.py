import pytest
from django.urls import reverse
from moto import mock_iot
from rest_framework import status
from shipchain_common.test_utils import JsonAsserterMixin
from shipchain_common.utils import random_id

from apps.shipments.models import TelemetryData


def add_telemetry_data_to_shipment(telemetry_data, shipment):
    for telemetry in telemetry_data:
        TelemetryData.objects.create(shipment=shipment,
                                     device=shipment.device,
                                     **telemetry)


@mock_iot
class TestPostTelemetryData(JsonAsserterMixin):
    @pytest.fixture(autouse=True)
    def set_up(self, device_alice_with_shipment, create_signed_telemetry_post):
        self.telemetry_url = reverse('device-telemetry', kwargs={'version': 'v1', 'pk': device_alice_with_shipment.id})
        self.random_telemetry_url = reverse('device-telemetry', kwargs={'version': 'v1', 'pk': random_id()})

    def test_unsigned_data_fails(self, no_user_api_client, create_unsigned_telemetry_post):
        response = no_user_api_client.post(self.telemetry_url, create_unsigned_telemetry_post)
        self.json_asserter.HTTP_400(response,
                                    error="This value does not match the required pattern.",
                                    pointer='payload')

    def test_signed_data_succeeds(self, no_user_api_client, create_signed_telemetry_post):
        response = no_user_api_client.post(self.telemetry_url, create_signed_telemetry_post)
        self.json_asserter.HTTP_204(response)
        assert TelemetryData.objects.all().count() == 1

    def test_invalid_signed_data_fails(self, no_user_api_client, invalid_post_signed_telemetry):
        response = no_user_api_client.post(self.telemetry_url, invalid_post_signed_telemetry)
        self.json_asserter.HTTP_400(response, error="This field is required.")

    def test_batch_signed_data_succeeds(self, no_user_api_client, create_batch_signed_telemetry_post):
        response = no_user_api_client.post(self.telemetry_url, create_batch_signed_telemetry_post)
        self.json_asserter.HTTP_204(response)
        assert TelemetryData.objects.all().count() == 2

    # TODO: HTTP_403 on shipchain_common
    def test_nonextant_device_fails(self, no_user_api_client, create_signed_telemetry_post):
        response = no_user_api_client.post(self.random_telemetry_url, create_signed_telemetry_post)
        # Error: "No shipment found associated to device."
        assert response.status_code == status.HTTP_403_FORBIDDEN

    # TODO: HTTP_405 on shipchain_common
    def test_no_get_calls(self, no_user_api_client):
        response = no_user_api_client.get(self.random_telemetry_url)
        assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED

    # TODO: HTTP_405 on shipchain_common
    def test_no_patch_calls(self, no_user_api_client, create_signed_telemetry_post):
        response = no_user_api_client.patch(self.random_telemetry_url, create_signed_telemetry_post)
        assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED

    # TODO: HTTP_405 on shipchain_common
    def test_no_del_calls(self, no_user_api_client):
        response = no_user_api_client.delete(self.random_telemetry_url)
        assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED


class TestRetrieveTelemetryData(JsonAsserterMixin):
    @pytest.fixture(autouse=True)
    def set_up(self, shipment_alice_with_device, create_signed_telemetry_post, shipment_alice, unsigned_telemetry):
        self.telemetry_url = reverse('shipment-telemetry-list', kwargs={'version': 'v1', 'shipment_pk': shipment_alice_with_device.id})
        self.empty_telemetry_url = reverse('shipment-telemetry-list', kwargs={'version': 'v1', 'shipment_pk': shipment_alice.id})
        self.random_telemetry_url = reverse('shipment-telemetry-list', kwargs={'version': 'v1', 'shipment_pk': random_id()})
        self.shipment_alice_with_device = shipment_alice_with_device
        add_telemetry_data_to_shipment([unsigned_telemetry], self.shipment_alice_with_device)
        self.unsigned_telemetry = unsigned_telemetry

    def test_unauthenticated_user_fails(self, no_user_api_client, mock_non_wallet_owner_calls):
        response = no_user_api_client.get(self.telemetry_url)
        # self.json_asserter.HTTP_403(response, vnd=False)
        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert response.json()['detail'] == 'You do not have permission to perform this action.'

    def test_random_shipment_url_fails(self, client_alice):
        response = client_alice.get(self.random_telemetry_url)
        # self.json_asserter.HTTP_403(response, vnd=False)
        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert response.json()['detail'] == 'You do not have permission to perform this action.'

    def test_non_shipment_owner_retrieves(self, client_bob, mock_successful_wallet_owner_calls):
        response = client_bob.get(self.telemetry_url)
        self.unsigned_telemetry.pop('version')
        self.json_asserter.HTTP_200(response, is_list=True, vnd=False, attributes=self.unsigned_telemetry)
        assert len(response.json()) == 1

    def test_shipment_owner_retrieves(self, client_alice):
        response = client_alice.get(self.telemetry_url)
        self.unsigned_telemetry.pop('version')
        self.json_asserter.HTTP_200(response, is_list=True, vnd=False, attributes=self.unsigned_telemetry)

    def test_filter_sensor(self, client_alice, unsigned_telemetry_different_sensor):
        add_telemetry_data_to_shipment([unsigned_telemetry_different_sensor],
                                       self.shipment_alice_with_device)
        response = client_alice.get(f'{self.telemetry_url}?sensor_id={self.unsigned_telemetry["sensor_id"]}')
        self.unsigned_telemetry.pop('version')
        self.json_asserter.HTTP_200(response, is_list=True, vnd=False, attributes=self.unsigned_telemetry)
        assert len(response.json()) == 1
        assert self.unsigned_telemetry['sensor_id'] != unsigned_telemetry_different_sensor['sensor_id']

    def test_filter_hardware_id(self, client_alice, unsigned_telemetry_different_hardware):
        add_telemetry_data_to_shipment([unsigned_telemetry_different_hardware],
                                       self.shipment_alice_with_device)
        response = client_alice.get(f'{self.telemetry_url}?hardware_id={self.unsigned_telemetry["hardware_id"]}')
        self.unsigned_telemetry.pop('version')
        self.json_asserter.HTTP_200(response, is_list=True, vnd=False, attributes=self.unsigned_telemetry)
        assert self.unsigned_telemetry['hardware_id'] != unsigned_telemetry_different_hardware['hardware_id']
        assert len(response.json()) == 1

    def test_permission_link_succeeds(self, no_user_api_client, permission_link_device_shipment):
        response = no_user_api_client.get(f'{self.telemetry_url}?permission_link={permission_link_device_shipment.id}')
        self.unsigned_telemetry.pop('version')
        self.json_asserter.HTTP_200(response, is_list=True, vnd=False, attributes=self.unsigned_telemetry)
        assert self.unsigned_telemetry in response.json()
        assert len(response.json()) == 1

    def test_unique_per_shipment(self, client_alice):
        response = client_alice.get(self.empty_telemetry_url)
        assert response.status_code == status.HTTP_200_OK
        assert len(response.json()) == 0
        assert TelemetryData.objects.all().count() == 1
