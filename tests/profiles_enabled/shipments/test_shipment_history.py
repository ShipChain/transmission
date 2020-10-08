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
from datetime import datetime, timedelta

import geojson
import pytest
from django.urls import reverse
from freezegun import freeze_time
from geojson import Point
from shipchain_common.test_utils import AssertionHelper, create_form_content
from shipchain_common.utils import random_id

from apps.documents.models import Document


class TestShipmentHistory:
    @pytest.fixture(autouse=True)
    def set_up(self, mocked_engine_rpc, mocked_iot_api, successful_wallet_owner_calls_assertions, shipment_alice,
               nonsuccessful_wallet_owner_calls_assertions):
        self.assert_success = successful_wallet_owner_calls_assertions
        self.assert_fail = nonsuccessful_wallet_owner_calls_assertions
        self.mocked_iot_api = mocked_iot_api

        self.shipment = shipment_alice

        self.history_url = reverse('shipment-history-list', kwargs={'version': 'v1', 'shipment_pk': shipment_alice.id})
        self.random_url = reverse('shipment-history-list', kwargs={'version': 'v1', 'shipment_pk': random_id()})
        self.update_url = reverse('shipment-detail', kwargs={'version': 'v1', 'pk': shipment_alice.id})

    def get_changed_fields(self, changes_list, field_name):
        return [item[field_name] for item in changes_list]

    def test_requires_authentication(self, api_client):
        response = api_client.get(self.history_url)
        AssertionHelper.HTTP_403(response, error='You do not have permission to perform this action.', vnd=False)

    def test_shipment_owner_can_access(self, client_alice):
        response = client_alice.get(self.history_url)
        AssertionHelper.HTTP_200(response, is_list=True, count=2)

        for old in self.get_changed_fields(response.json()['data'][1]['fields'], 'old'):
            assert old is None

        assert 'vault_uri' in self.get_changed_fields(response.json()['data'][0]['fields'], 'field')
        assert 'version' not in self.get_changed_fields(response.json()['data'][1]['fields'], 'field')
        # On shipment creation, the most recent change is from a background task. Should have a null author.

        assert response.json()['data'][0]['author'] is None

    def test_org_member_can_access(self, client_carol):
        response = client_carol.get(self.history_url)
        AssertionHelper.HTTP_200(response, is_list=True)

    def test_wallet_owner_succeeds(self, client_bob, mock_successful_wallet_owner_calls):
        response = client_bob.get(self.history_url)
        AssertionHelper.HTTP_200(response, is_list=True)
        mock_successful_wallet_owner_calls.assert_calls(self.assert_success)

    def test_nonwallet_owner_fails(self, client_bob, mock_non_wallet_owner_calls):
        response = client_bob.get(self.history_url)
        AssertionHelper.HTTP_403(response, error='You do not have permission to perform this action.', vnd=False)
        mock_non_wallet_owner_calls.assert_calls(self.assert_fail)

    def test_random_id_fails(self, client_bob):
        response = client_bob.get(self.random_url)
        AssertionHelper.HTTP_403(response, error='You do not have permission to perform this action.', vnd=False)

    def test_shipment_udate_fields(self, client_bob, mock_successful_wallet_owner_calls, user_bob_id):
        response = client_bob.patch(self.update_url, data={'carriers_scac': 'carrier_scac', 'pickup_act': datetime.utcnow()})
        AssertionHelper.HTTP_202(response)
        mock_successful_wallet_owner_calls.assert_calls(self.assert_success)

        response = client_bob.get(self.history_url)
        AssertionHelper.HTTP_200(response, is_list=True, count=3)
        mock_successful_wallet_owner_calls.assert_calls(self.assert_success)
        changed_fields = self.get_changed_fields(response.json()['data'][0]['fields'], 'field')
        assert 'carriers_scac' in changed_fields
        assert 'updated_by' in changed_fields
        assert 'pickup_act' not in changed_fields

        assert response.json()['data'][0]['author'] == user_bob_id

    def test_shipment_udate_customer_fields(self, client_alice):
        response = client_alice.patch(self.update_url, data={
            'customer_fields': {
                'custom_field_1': 'value one',
                'custom_field_2': 'value two'
            }
        })
        AssertionHelper.HTTP_202(response)

        response = client_alice.get(self.history_url)
        AssertionHelper.HTTP_200(response, is_list=True, count=3)
        changed_fields = self.get_changed_fields(response.json()['data'][0]['fields'], 'field')
        assert 'customer_fields.custom_field_1' in changed_fields
        assert 'customer_fields.custom_field_2' in changed_fields

        response = client_alice.patch(self.update_url, data={
            'customer_fields': {
                'custom_field_2': 'new value two'
            }
        })
        AssertionHelper.HTTP_202(response)

        response = client_alice.get(self.history_url)
        AssertionHelper.HTTP_200(response, is_list=True, count=4)
        changed_fields = self.get_changed_fields(response.json()['data'][0]['fields'], 'field')
        assert 'customer_fields.custom_field_1' not in changed_fields
        assert 'customer_fields.custom_field_2' in changed_fields

    def test_shipment_udate_location(self, client_alice):
        location_attributes, content_type = create_form_content({
            'ship_from_location.name': "Location Name",
            'ship_from_location.city': "City",
            'ship_from_location.state': "State",
            'ship_from_location.geometry': geojson.dumps(Point((42.0, 27.0)))
        })

        response = client_alice.patch(self.update_url, data=location_attributes, content_type=content_type)
        AssertionHelper.HTTP_202(response)

        response = client_alice.get(self.history_url)
        AssertionHelper.HTTP_200(response, is_list=True, count=3)
        changed_fields = self.get_changed_fields(response.json()['data'][0]['fields'], 'field')
        assert 'ship_from_location' in changed_fields
        assert 'geometry' not in self.get_changed_fields(response.json()['data'][0]['relationships']['ship_from_location'], 'field')
        assert 'ship_from_location' in response.json()['data'][0]['relationships'].keys()

        location_attributes, content_type = create_form_content({
            'ship_from_location.phone_number': '555-555-5555'
        })

        response = client_alice.patch(self.update_url, data=location_attributes, content_type=content_type)
        AssertionHelper.HTTP_202(response)

        response = client_alice.get(self.history_url)
        AssertionHelper.HTTP_200(response, is_list=True, count=4)
        ship_from_location_changes = response.json()['data'][0]['relationships']['ship_from_location']
        assert 'phone_number' in self.get_changed_fields(ship_from_location_changes, 'field')

    def test_history_documents(self, client_alice):
        document = Document.objects.create(name='Test Historical', owner_id=self.shipment.owner_id, shipment=self.shipment)
        response = client_alice.get(self.history_url)
        AssertionHelper.HTTP_200(response, is_list=True, count=2)
        # A document in upload_status pending shouldn't be present in the shipment diff history
        assert response.json()['data'][0]['relationships'] is None

        # A document with upload_status complete should be present in the shipment history
        document.upload_status = 1
        document.save()
        response = client_alice.get(self.history_url)
        AssertionHelper.HTTP_200(response, is_list=True, count=3)
        history_documents = response.json()['data'][0]['relationships'].get('documents')
        assert history_documents
        assert 'upload_status' in self.get_changed_fields(history_documents['fields'], 'field')

        # Any subsequent document object update should be present in the diff change
        document.description = 'Document updated with some description for example'
        document.save()

        response = client_alice.get(self.history_url)
        AssertionHelper.HTTP_200(response, is_list=True, count=4)
        history_documents = response.json()['data'][0]['relationships'].get('documents')
        assert history_documents
        assert 'description' in self.get_changed_fields(history_documents['fields'], 'field')

    def test_enum_representation(self, client_alice):
        shipment_action_url = reverse('shipment-actions', kwargs={'version': 'v1', 'shipment_pk': self.shipment.id})
        response = client_alice.post(shipment_action_url, {'action_type': 'Pick_up'})
        AssertionHelper.HTTP_200(response)

        response = client_alice.get(self.history_url)
        AssertionHelper.HTTP_200(response, is_list=True, count=3)

        changed_fields = self.get_changed_fields(response.json()['data'][0]['fields'], 'field')
        assert 'state' in changed_fields
        assert 'pickup_act' in changed_fields

        for change in response.json()['data'][0]['fields']:
            if change['field'] == 'state':
                # Enum field value should be in their character representation
                assert change['new'] == 'IN_TRANSIT'

    def test_history_filtering(self, client_alice):
        initial_datetime = datetime.now()
        one_day_later = datetime.now() + timedelta(days=1)
        two_day_later = datetime.now() + timedelta(days=2)
        # We update the shipment 1 day in the future

        with freeze_time(one_day_later.isoformat()) as date_in_future:
            response = client_alice.patch(self.update_url, {'container_qty': '1'})
            AssertionHelper.HTTP_202(response)

            # We set the clock to two days in the future
            date_in_future.move_to(two_day_later)
            response = client_alice.patch(self.update_url, {'package_qty': '10'})
            AssertionHelper.HTTP_202(response)

        response = client_alice.get(self.history_url)
        AssertionHelper.HTTP_200(response, is_list=True, count=4)
        assert 'package_qty' in self.get_changed_fields(response.json()['data'][0]['fields'], 'field')

        response = client_alice.get(f'{self.history_url}?history_date__lte={initial_datetime.isoformat()}')
        AssertionHelper.HTTP_200(response, is_list=True, count=2)
        assert 'package_qty' not in self.get_changed_fields(response.json()['data'][0]['fields'], 'field')

        response = client_alice.get(f'{self.history_url}?history_date__gte={initial_datetime.isoformat()}')
        AssertionHelper.HTTP_200(response, is_list=True, count=2)
        assert 'package_qty' in self.get_changed_fields(response.json()['data'][0]['fields'], 'field')
        assert 'container_qty' in self.get_changed_fields(response.json()['data'][1]['fields'], 'field')

        response = client_alice.get(f'{self.history_url}?history_date__lte={one_day_later.isoformat()}' \
                                    f'&history_date__gte={datetime.now().isoformat()}')
        AssertionHelper.HTTP_200(response, is_list=True, count=1)
        assert 'container_qty' in self.get_changed_fields(response.json()['data'][0]['fields'], 'field')
