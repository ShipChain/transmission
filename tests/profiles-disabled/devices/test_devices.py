import pytest
from django.urls import reverse
from shipchain_common.test_utils import AssertionHelper


class TestSensorsWithShipmentList:
    @pytest.fixture(autouse=True)
    def set_up(self, shipment_with_device):
        self.url = reverse('device-sensors', kwargs={'version': 'v1', 'device_pk': shipment_with_device.device_id})

    def test_unauthenticated_user_fails(self, api_client):
        response = api_client.get(self.url)
        AssertionHelper.HTTP_405(response, vnd=False, error='Unable to list sensors when not profiles is not enabled.')
