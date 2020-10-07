import pytest
from datetime import datetime, timedelta

from django.core.cache import cache
from freezegun import freeze_time
from rest_framework import status
from rest_framework.reverse import reverse
from shipchain_common.test_utils import replace_variables_in_string


MONTHLY_THROTTLE_RATE = 1
VAULT_ID = 'TEST_VAULT_ID'


class TestShipmentAPIThrottling:
    @pytest.fixture(autouse=True)
    def set_up(self, profiles_ids):
        cache.clear()

        self.variables = {
            '_vault_id': VAULT_ID,
            '_vault_uri': 's3://bucket/' + VAULT_ID,
            '_carrier_wallet_id': profiles_ids['carrier_wallet_id'],
            '_shipper_wallet_id': profiles_ids['shipper_wallet_id'],
            '_storage_credentials_id': profiles_ids['storage_credentials_id'],
            '_async_hash': 'txHash'
        }

        self.post_template = '''
            {
              "data": {
                "type": "Shipment",
                "attributes": {
                  "carrier_wallet_id": "<<_carrier_wallet_id>>",
                  "shipper_wallet_id": "<<_shipper_wallet_id>>",
                  "storage_credentials_id": "<<_storage_credentials_id>>"
                }
              }
            }
        '''

    def test_throttling(self, client_alice_throttled, client_lionel, client_carol_throttled, mock_successful_wallet_owner_calls, mocked_profiles_wallet_list, mocked_engine_rpc, mocked_iot_api):
        url = reverse('shipment-list', kwargs={'version': 'v1'})

        post_data = replace_variables_in_string(self.post_template, self.variables)

        # First call should succeed
        response = client_alice_throttled.post(url, post_data, content_type='application/vnd.api+json')
        assert response.status_code == status.HTTP_202_ACCEPTED

        # Calls exceeding the throttle should fail
        response = client_alice_throttled.post(url, post_data, content_type='application/vnd.api+json')
        assert response.status_code == status.HTTP_429_TOO_MANY_REQUESTS

        # GET Calls should still succeed
        response = client_alice_throttled.get(url)
        assert response.status_code == status.HTTP_200_OK

        # Calls exceeding the throttle should fail for any member in the org
        response = client_alice_throttled.post(url, post_data, content_type='application/vnd.api+json')
        assert response.status_code == status.HTTP_429_TOO_MANY_REQUESTS

        one_month_later = datetime.now() + timedelta(days=32)

        with freeze_time(one_month_later):
            # First call should succeed
            response = client_carol_throttled.post(url, post_data, content_type='application/vnd.api+json')
            assert response.status_code == status.HTTP_202_ACCEPTED

            # Calls exceeding the throttle should fail
            response = client_carol_throttled.post(url, post_data, content_type='application/vnd.api+json')
            assert response.status_code == status.HTTP_429_TOO_MANY_REQUESTS

        # Call for someone not in an org should succeed
        response = client_lionel.post(url, post_data, content_type='application/vnd.api+json')
        assert response.status_code == status.HTTP_202_ACCEPTED
