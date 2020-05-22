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
from unittest import mock

import pytest
from django.conf import settings
from django.urls import reverse
from moto import mock_sns
from shipchain_common.test_utils import AssertionHelper, create_form_content
from shipchain_common.utils import random_id
from copy import deepcopy

from apps.shipments.models import Shipment, Location, TrackingData


class TestShipmentMethods:
    @pytest.fixture(autouse=True)
    def set_up(self, mocked_engine_rpc, mocked_iot_api):
        return

    def test_get_device_request_url(self, shipment_alice_with_device):
        profiles_url = shipment_alice_with_device.get_device_request_url()

        assert settings.PROFILES_URL in profiles_url
        assert f"?on_shipment={shipment_alice_with_device.vault_id}" in profiles_url


class TestShipmentAftershipQuickadd:
    create_url = reverse('shipment-list', kwargs={'version': 'v1'})

    @pytest.fixture(autouse=True)
    def set_up(self, profiles_ids, mocked_engine_rpc):
        self.profiles_ids = profiles_ids
        self.base_create_attributes = {
            'storage_credentials_id': profiles_ids['storage_credentials_id'],
            'shipper_wallet_id': profiles_ids['shipper_wallet_id'],
            'carrier_wallet_id': profiles_ids['carrier_wallet_id'],
            'aftership_tracking': 'aftership_tracking'
        }

    @pytest.fixture
    def mock_aftership_validation_succeess(self, mock_successful_wallet_owner_calls):
        mock_successful_wallet_owner_calls.register_uri(mock_successful_wallet_owner_calls.POST,
                                                        f'{settings.AFTERSHIP_URL}couriers/detect',
                                                        )
        return mock_successful_wallet_owner_calls

    @pytest.fixture
    def mock_aftership_validation_failure(self, mock_successful_wallet_owner_calls):
        mock_successful_wallet_owner_calls.register_uri(mock_successful_wallet_owner_calls.POST,
                                                        f'{settings.AFTERSHIP_URL}couriers/detect',
                                                        status=400
                                                        )
        return mock_successful_wallet_owner_calls

    @pytest.fixture
    def mock_aftership_create_success(self, mock_aftership_validation_succeess):
        mock_aftership_validation_succeess.register_uri(mock_aftership_validation_succeess.POST,
                                                        f'{settings.AFTERSHIP_URL}trackings',
                                                        body=json.dumps({'data': {'tracking': {'id': 'id'}}}),)
        return mock_aftership_validation_succeess

    @pytest.fixture
    def mock_aftership_create_fail(self, mock_aftership_validation_succeess):
        mock_aftership_validation_succeess.register_uri(mock_aftership_validation_succeess.POST,
                                                        f'{settings.AFTERSHIP_URL}trackings',
                                                        status=400)
        return mock_aftership_validation_succeess

    @pytest.fixture(autouse=True)
    def mock_sns(self):
        mock_sns().start()
        import boto3
        settings.BOTO3_SESSION = boto3.Session(region_name='us-east-1')
        settings.SNS_CLIENT = settings.BOTO3_SESSION.client('sns')
        settings.SNS_CLIENT.create_topic(Name='transmission-events-test')

    @pytest.fixture
    def assertions_aftership_validation(self, successful_shipment_create_profiles_assertions):
        successful_shipment_create_profiles_assertions.append({
                'host': settings.AFTERSHIP_URL.replace('/v4/', ''),
                'path': '/v4/couriers/detect',
                'body': {'tracking': {'tracking_number': self.base_create_attributes['aftership_tracking']}}
            })
        return successful_shipment_create_profiles_assertions

    @pytest.fixture
    def assertions_create_tracking(self, assertions_aftership_validation):
        assertions_aftership_validation.append({
                'host': settings.AFTERSHIP_URL.replace('/v4/', ''),
                'path': '/v4/trackings',
                'body': {'tracking': {'tracking_number': self.base_create_attributes['aftership_tracking']}}
            })
        return assertions_aftership_validation

    def test_successful_quickadd(self, client_alice, mock_aftership_create_success, assertions_create_tracking):
        response = client_alice.post(self.create_url, self.base_create_attributes)
        AssertionHelper.HTTP_202(response,
                                 entity_refs=AssertionHelper.EntityRef(
                                     resource='Shipment',
                                     attributes=self.base_create_attributes
                                 ))
        mock_aftership_create_success.assert_calls(assertions_create_tracking)

    def test_quickadd_create_fail(self, client_alice, mock_aftership_create_fail, assertions_create_tracking):
        response = client_alice.post(self.create_url, self.base_create_attributes)
        AssertionHelper.HTTP_400(response, error='Supplied tracking number has already been imported into Aftership')
        mock_aftership_create_fail.assert_calls(assertions_create_tracking)

    def test_quickadd_validation_fail(self, client_alice, mock_aftership_validation_failure,
                                      assertions_aftership_validation):
        response = client_alice.post(self.create_url, self.base_create_attributes)
        AssertionHelper.HTTP_400(response, error='Invalid aftership_tracking value')
        mock_aftership_validation_failure.assert_calls(assertions_aftership_validation)


class TestShipmentsList:
    url = reverse('shipment-list', kwargs={'version': 'v1'})

    @pytest.fixture(autouse=True)
    def set_up(self, mocked_engine_rpc, mocked_iot_api, profiles_wallet_list_assertions):
        self.profiles_assertions = profiles_wallet_list_assertions

    def test_requires_authentication(self, api_client):
        response = api_client.get(self.url)
        AssertionHelper.HTTP_403(response)

    def test_list_empty(self, client_alice, mocked_profiles_wallet_list):
        response = client_alice.get(self.url)
        AssertionHelper.HTTP_200(response, count=0, is_list=True)
        mocked_profiles_wallet_list.assert_calls(self.profiles_assertions)

    def test_retrieves_organization_shipments(self, client_carol, client_alice, alice_organization_shipment_fixtures,
                                              client_bob, bob_organization_shipment_fixtures, mocked_profiles_wallet_list):
        response = client_alice.get(self.url)
        AssertionHelper.HTTP_200(response, is_list=True,
                                 entity_refs=alice_organization_shipment_fixtures,
                                 count=len(alice_organization_shipment_fixtures))
        mocked_profiles_wallet_list.assert_calls(self.profiles_assertions)

        response = client_carol.get(self.url)
        AssertionHelper.HTTP_200(response, is_list=True,
                                 entity_refs=alice_organization_shipment_fixtures,
                                 count=len(alice_organization_shipment_fixtures))
        mocked_profiles_wallet_list.assert_calls(self.profiles_assertions)

        response = client_bob.get(self.url)
        AssertionHelper.HTTP_200(response, is_list=True,
                                 entity_refs=bob_organization_shipment_fixtures,
                                 count=len(bob_organization_shipment_fixtures))
        mocked_profiles_wallet_list.assert_calls(self.profiles_assertions)

    def test_retrieves_profiles_wallets_shipments(self, client_bob, bob_organization_shipment_fixtures, profiles_ids,
                                                  alice_organization_shipment_fixtures, modified_http_pretty):
        modified_http_pretty.register_uri(modified_http_pretty.GET,
                                          f"{settings.PROFILES_URL}/api/v1/wallet",
                                          body=json.dumps({'data': [
                                              {'id': profiles_ids['carrier_wallet_id']},
                                              {'id': profiles_ids['shipper_wallet_id']},
                                          ]}), status=200)

        response = client_bob.get(self.url)
        AssertionHelper.HTTP_200(response, is_list=True,
                                 entity_refs=[*bob_organization_shipment_fixtures, *alice_organization_shipment_fixtures],
                                 count=len([*bob_organization_shipment_fixtures, *alice_organization_shipment_fixtures]))
        modified_http_pretty.assert_calls(self.profiles_assertions)

    def test_filter_shipments(self, client_alice, alice_organization_shipment_fixtures, alice_organization_shipments,
                              mocked_profiles_wallet_list):
        location = Location.objects.create(name="location")
        alice_organization_shipments[0].mode_of_transport_code = 'mode'
        alice_organization_shipments[0].ship_to_location = location
        alice_organization_shipments[0].customer_fields = {'string': 'string'}
        alice_organization_shipments[0].pick_up()
        alice_organization_shipments[0].save()
        alice_organization_shipment_fixtures[0].attributes = {'mode_of_transport_code': 'mode', 'customer_fields': {'string': 'string'}, 'state': 'IN_TRANSIT'}
        alice_organization_shipment_fixtures[0].relationships = [{'ship_to_location': AssertionHelper.EntityRef(resource='Location', pk=location.id)}]
        response = client_alice.get(f'{self.url}?mode_of_transport_code=mode')
        AssertionHelper.HTTP_200(response, is_list=True,
                                 entity_refs=alice_organization_shipment_fixtures[0],
                                 count=1)
        mocked_profiles_wallet_list.assert_calls(self.profiles_assertions)

        response = client_alice.get(f'{self.url}?has_ship_to_location=True')
        AssertionHelper.HTTP_200(response, is_list=True,
                                 entity_refs=alice_organization_shipment_fixtures[0],
                                 count=1)
        mocked_profiles_wallet_list.assert_calls(self.profiles_assertions)

        response = client_alice.get(f'{self.url}?state=IN_TRANSIT')
        AssertionHelper.HTTP_200(response, is_list=True,
                                 entity_refs=alice_organization_shipment_fixtures[0],
                                 count=1)
        mocked_profiles_wallet_list.assert_calls(self.profiles_assertions)

        response = client_alice.get(f'{self.url}?state=string')
        AssertionHelper.HTTP_400(response)
        mocked_profiles_wallet_list.assert_calls(self.profiles_assertions)

    def test_ordering(self, client_alice, alice_organization_shipment_fixtures, alice_organization_shipments,
                      mocked_profiles_wallet_list):
        alice_organization_shipments[0].pickup_est = datetime.utcnow()
        alice_organization_shipments[0].save()
        alice_organization_shipments[1].pickup_est = datetime.utcnow() - timedelta(days=1)
        alice_organization_shipments[1].save()
        alice_organization_shipments[2].pickup_est = datetime.utcnow() - timedelta(days=2)
        alice_organization_shipments[2].save()
        alice_organization_shipment_fixtures[0].attributes['pickup_est'] = datetime.utcnow().isoformat()
        alice_organization_shipment_fixtures[1].attributes['pickup_est'] = (datetime.utcnow() - timedelta(days=1)).isoformat()
        alice_organization_shipment_fixtures[2].attributes['pickup_est'] = (datetime.utcnow() - timedelta(days=2)).isoformat()
        response = client_alice.get(self.url)
        AssertionHelper.HTTP_200(response, is_list=True,
                                 entity_refs=alice_organization_shipment_fixtures.reverse(),
                                 count=len(alice_organization_shipment_fixtures))
        mocked_profiles_wallet_list.assert_calls(self.profiles_assertions)

    def test_search(self, client_alice, alice_organization_shipment_fixtures, alice_organization_shipments,
                    mocked_profiles_wallet_list):
        location = Location.objects.create(name="location")
        alice_organization_shipments[0].shippers_reference = 'Shipper Reference'
        alice_organization_shipments[0].ship_to_location = location
        alice_organization_shipments[0].save()
        alice_organization_shipment_fixtures[0].attributes = {'shippers_reference': 'Shipper Reference'}
        alice_organization_shipment_fixtures[0].relationships = [{'ship_to_location': AssertionHelper.EntityRef(resource='Location', pk=location.id)}]
        response = client_alice.get(f'{self.url}?search={location.name}')
        AssertionHelper.HTTP_200(response, is_list=True,
                                 entity_refs=alice_organization_shipment_fixtures[0],
                                 count=1)
        mocked_profiles_wallet_list.assert_calls(self.profiles_assertions)

        response = client_alice.get(f'{self.url}?search=Shipper Reference')
        AssertionHelper.HTTP_200(response, is_list=True,
                                 entity_refs=alice_organization_shipment_fixtures[0],
                                 count=1)
        mocked_profiles_wallet_list.assert_calls(self.profiles_assertions)

        response = client_alice.get(f'{self.url}?search=No valid shipments')
        AssertionHelper.HTTP_200(response, is_list=True, count=0)
        mocked_profiles_wallet_list.assert_calls(self.profiles_assertions)

    def test_customer_fields_filter(self, client_alice, alice_organization_shipment_fixtures, alice_organization_shipments,
                                    mocked_profiles_wallet_list):
        customer_fields = {
            'number': 8675309,
            'boolean': True,
            'datetime': datetime.utcnow().isoformat(),
            'array': ["A", "B", "C"],
            'decimal': 3.14
        }
        alice_organization_shipments[0].customer_fields = customer_fields
        alice_organization_shipments[0].save()
        alice_organization_shipment_fixtures[0].attributes['customer_fields'] = customer_fields
        for key, value in customer_fields.items():
            response = client_alice.get(f'{self.url}?customer_fields__{key}={json.dumps(value)}')
            AssertionHelper.HTTP_200(response, is_list=True,
                                     entity_refs=alice_organization_shipment_fixtures[0],
                                     count=1)
            mocked_profiles_wallet_list.assert_calls(self.profiles_assertions)


class TestShipmentDetail:
    @pytest.fixture(autouse=True)
    def set_up(self, mocked_engine_rpc, mocked_iot_api, shipment_alice, successful_wallet_owner_calls_assertions,
               nonsuccessful_wallet_owner_calls_assertions):
        self.url = reverse('shipment-detail', kwargs={'version': 'v1', 'pk': shipment_alice.id})
        self.random_url = reverse('shipment-detail', kwargs={'version': 'v1', 'pk': random_id()})
        self.assert_success = successful_wallet_owner_calls_assertions
        self.assert_fail = nonsuccessful_wallet_owner_calls_assertions

    def test_requires_authentication(self, api_client):
        response = api_client.get(self.url)
        AssertionHelper.HTTP_403(response)

    def test_shipment_owner_can_access(self, client_alice, entity_ref_shipment_alice):
        response = client_alice.get(self.url)
        AssertionHelper.HTTP_200(response, entity_refs=entity_ref_shipment_alice)

    def test_org_member_can_access(self, client_carol, entity_ref_shipment_alice):
        response = client_carol.get(self.url)
        AssertionHelper.HTTP_200(response, entity_refs=entity_ref_shipment_alice)

    def test_wallet_owner_succeeds(self, client_bob, entity_ref_shipment_alice, mock_successful_wallet_owner_calls):
        response = client_bob.get(self.url)
        AssertionHelper.HTTP_200(response, entity_refs=entity_ref_shipment_alice)
        mock_successful_wallet_owner_calls.assert_calls(self.assert_success)

    def test_nonwallet_owner_fails(self, client_bob, entity_ref_shipment_alice, mock_non_wallet_owner_calls):
        response = client_bob.get(self.url)
        AssertionHelper.HTTP_403(response)
        mock_non_wallet_owner_calls.assert_calls(self.assert_fail)

    def test_random_id_fails(self, client_bob):
        response = client_bob.get(self.random_url)
        AssertionHelper.HTTP_403(response)


class TestShipmentDelete:
    @pytest.fixture(autouse=True)
    def set_up(self, mocked_engine_rpc, mocked_iot_api, shipment_alice, successful_wallet_owner_calls_assertions):
        self.url = reverse('shipment-detail', kwargs={'version': 'v1', 'pk': shipment_alice.id})
        self.random_url = reverse('shipment-detail', kwargs={'version': 'v1', 'pk': random_id()})
        self.assert_success = successful_wallet_owner_calls_assertions

    def test_requires_authentication(self, api_client):
        response = api_client.delete(self.url)
        AssertionHelper.HTTP_403(response)

    def test_shipment_owner_can_delete(self, client_alice):
        response = client_alice.delete(self.url)
        AssertionHelper.HTTP_204(response)

    def test_org_member_can_delete(self, client_carol):
        response = client_carol.delete(self.url)
        AssertionHelper.HTTP_204(response)

    def test_wallet_owner_fails(self, client_bob, entity_ref_shipment_alice, mock_successful_wallet_owner_calls):
        response = client_bob.delete(self.url)
        AssertionHelper.HTTP_403(response)
        # Wallet owner calls shouldn't even be made so cannot test assertions

    def test_random_id_fails(self, client_bob):
        response = client_bob.delete(self.random_url)
        AssertionHelper.HTTP_404(response)


class TestShipmentUpdate:
    @pytest.fixture(autouse=True)
    def set_up(self, mocked_engine_rpc, mocked_iot_api, shipment_alice, entity_ref_shipment_alice,
               successful_wallet_owner_calls_assertions, nonsuccessful_wallet_owner_calls_assertions):
        self.url = reverse('shipment-detail', kwargs={'version': 'v1', 'pk': shipment_alice.id})
        self.random_url = reverse('shipment-detail', kwargs={'version': 'v1', 'pk': random_id()})
        self.entity_ref = entity_ref_shipment_alice
        self.entity_ref.attributes = {"carriers_scac": "carriers_scac"}
        self.shipment = shipment_alice
        self.assert_success = successful_wallet_owner_calls_assertions
        self.assert_fail = nonsuccessful_wallet_owner_calls_assertions
        self.mocked_iot_api = mocked_iot_api

    def test_requires_authentication(self, api_client):
        response = api_client.patch(self.url, data={"carriers_scac": "carriers_scac"})
        AssertionHelper.HTTP_403(response)

    def test_shipment_owner_can_update(self, client_alice):
        response = client_alice.patch(self.url,
                                      data={"carriers_scac": "carriers_scac", "asset_physical_id": "asset_physical_id"})
        AssertionHelper.HTTP_202(response, entity_refs=self.entity_ref)

        # Asset Physical Id cannot be set in update
        assert "asset_physical_id" not in response.json()['data']
        self.shipment.refresh_from_db(fields=["asset_physical_id"])
        assert not self.shipment.asset_physical_id

    def test_org_member_can_update(self, client_carol):
        response = client_carol.patch(self.url, data={"carriers_scac": "carriers_scac"})
        AssertionHelper.HTTP_202(response, entity_refs=self.entity_ref)

    def test_wallet_owner_succeeds(self, client_bob, mock_successful_wallet_owner_calls):
        response = client_bob.patch(self.url, data={"carriers_scac": "carriers_scac"})
        AssertionHelper.HTTP_202(response, entity_refs=self.entity_ref)
        mock_successful_wallet_owner_calls.assert_calls(self.assert_success)

    def test_nonwallet_owner_fails(self, client_bob, mock_non_wallet_owner_calls):
        response = client_bob.patch(self.url, data={"carriers_scac": "carriers_scac"})
        AssertionHelper.HTTP_403(response)
        mock_non_wallet_owner_calls.assert_calls(self.assert_fail)

    def test_random_id_fails(self, client_bob):
        response = client_bob.patch(self.random_url, data={"carriers_scac": "carriers_scac"})
        AssertionHelper.HTTP_403(response)

    def test_put_fails(self, client_alice):
        response = client_alice.put(self.url, data={"carriers_scac": "carriers_scac"})
        AssertionHelper.HTTP_405(response)

    def test_gtx_update_permissions(self, client_carol, client_gtx_alice):
        response = client_carol.patch(self.url, data={"gtx_required": True})
        AssertionHelper.HTTP_403(response, error='User does not have access to modify GTX for this shipment')

        self.entity_ref.attributes = {"gtx_required": True}
        response = client_gtx_alice.patch(self.url, data={"gtx_required": True})
        AssertionHelper.HTTP_202(response, entity_refs=self.entity_ref)

    def test_gtx_requires_before_pickup(self, client_gtx_alice):
        self.shipment.pick_up()
        self.shipment.save()
        response = client_gtx_alice.patch(self.url, data={"gtx_required": True})
        AssertionHelper.HTTP_400(response, error='Cannot modify GTX for a shipment in progress')

    def test_update_with_location_mapbox(self, client_alice, mock_location):
        self.entity_ref.attributes = None
        location_attributes, content_type = create_form_content({
            'ship_from_location.name': "Location Name",
            'ship_from_location.city': "City",
            'ship_from_location.state': "State"
        })

        response = client_alice.patch(self.url, data=location_attributes, content_type=content_type)
        self.entity_ref.relationships = [{
            'ship_from_location': AssertionHelper.EntityRef(resource='Location')
        }]
        self.shipment.refresh_from_db(fields=['ship_from_location'])
        AssertionHelper.HTTP_202(
            response,
            entity_refs=self.entity_ref,
            included=[AssertionHelper.EntityRef(resource='Location',
                                                pk=self.shipment.ship_from_location.id,
                                                attributes={
                                                    'name': "Location Name",
                                                    'city': "City",
                                                    'state': "State",
                                                    'geometry': {'coordinates': [42.0, 27.0], 'type': 'Point'}
                                                })]
        )
        mock_location.assert_calls([{
            'host': 'https://api.mapbox.com',
            'path': '/geocoding/v5/mapbox.places/,%20City,%20State.json',
        }])

    # It is only possible to test location with google OR mapbox due to how the token is gathered by geocoder.
    # We will default to testing with mapbox as that is what is currently used on ShipChain's Transmission services,
    # But this is the test necessary to check the google API call.
    # def test_update_with_location_google(self, client_alice, mock_location):
    #     self.entity_ref.attributes = None
    #     location_attributes, content_type = create_form_content({
    #         'ship_from_location.name': "Location Name",
    #         'ship_from_location.city': "City",
    #         'ship_from_location.state': "State"
    #     })
    #
    #     response = client_alice.patch(self.url, data=location_attributes, content_type=content_type)
    #     self.entity_ref.relationships = [{
    #         'ship_from_location': AssertionHelper.EntityRef(resource='Location')
    #     }]
    #     self.shipment.refresh_from_db(fields=['ship_from_location'])
    #     AssertionHelper.HTTP_202(
    #         response,
    #         entity_refs=self.entity_ref,
    #         included=[AssertionHelper.EntityRef(resource='Location',
    #                                             pk=self.shipment.ship_from_location.id,
    #                                             attributes={
    #                                                 'name': "Location Name",
    #                                                 'city': "City",
    #                                                 'state': "State",
    #                                                 'geometry': {'coordinates': [23.0, 12.0], 'type': 'Point'}
    #                                             })]
    #     )
    #     mock_location.assert_calls([{
    #         'host': 'https://maps.googleapis.com',
    #         'path': '/maps/api/geocode/json',
    #         'query': {'address': ', City, State'},
    #     }])

    def test_update_with_multiple_locations(self, client_alice, mock_location):
        self.entity_ref.attributes = None
        location_attributes, content_type = create_form_content({
            'ship_from_location.name': "Location Name",
            'ship_from_location.city': "City",
            'ship_from_location.state': "State",
            'ship_to_location.name': "Location Name",
            'ship_to_location.city': "City",
            'ship_to_location.state': "State",
        })

        response = client_alice.patch(self.url, data=location_attributes, content_type=content_type)
        self.entity_ref.relationships = [{
            'ship_from_location': AssertionHelper.EntityRef(resource='Location')
        }]
        self.shipment.refresh_from_db(fields=['ship_from_location', 'ship_to_location'])
        AssertionHelper.HTTP_202(
            response,
            entity_refs=self.entity_ref,
            included=[AssertionHelper.EntityRef(resource='Location',
                                                pk=self.shipment.ship_from_location.id,
                                                attributes={
                                                    'name': "Location Name",
                                                    'city': "City",
                                                    'state': "State",
                                                    'geometry': {'coordinates': [42.0, 27.0], 'type': 'Point'}
                                                }),
                      AssertionHelper.EntityRef(resource='Location',
                                                pk=self.shipment.ship_to_location.id,
                                                attributes={
                                                    'name': "Location Name",
                                                    'city': "City",
                                                    'state': "State",
                                                    'geometry': {'coordinates': [42.0, 27.0], 'type': 'Point'}
                                                })
                      ]
        )
        mock_location.assert_calls([{
            'host': 'https://api.mapbox.com',
            'path': '/geocoding/v5/mapbox.places/,%20City,%20State.json',
        }, {
            'host': 'https://api.mapbox.com',
            'path': '/geocoding/v5/mapbox.places/,%20City,%20State.json',
        }])

    def test_update_customer_fields(self, client_alice):
        response = client_alice.patch(self.url, data={
            'customer_fields': {
                'field_1': 'value_1',
                'field_2': 'value_2',
            }
        })
        self.entity_ref.attributes = {
            'customer_fields': {
                'field_1': 'value_1',
                'field_2': 'value_2',
            }
        }
        AssertionHelper.HTTP_202(response, entity_refs=self.entity_ref)

        response = client_alice.patch(self.url, data={
            'customer_fields': {
                'field_3': 'value_3',
                'field_2': 'value_2 updated',
            }
        })
        self.entity_ref.attributes = {
            'customer_fields': {
                'field_1': 'value_1',
                'field_2': 'value_2 updated',
                'field_3': 'value_3'
            }
        }
        AssertionHelper.HTTP_202(response, entity_refs=self.entity_ref)

    def test_update_with_device(self, client_alice, device):
        with mock.patch('apps.shipments.models.Device.get_or_create_with_permission') as mock_device:
            mock_device.return_value = device

            call_count = self.mocked_iot_api.call_count
            self.entity_ref.attributes = None
            self.entity_ref.relationships = [{'device': AssertionHelper.EntityRef(resource='Device', pk=device.id)}]

            response = client_alice.patch(self.url, data={'device_id': device.id})
            AssertionHelper.HTTP_202(response, entity_refs=self.entity_ref)

            mock_device.assert_called()
            self.mocked_iot_api.call_count = call_count + 1

    def test_update_with_unavailable_device(self, client_alice, device, modified_http_pretty):
        modified_http_pretty.register_uri(modified_http_pretty.GET,
                                          f'{settings.PROFILES_URL}/api/v1/device/{device.id}/?is_active',
                                          status=400)

        response = client_alice.patch(self.url, data={'device_id': device.id})
        AssertionHelper.HTTP_400(response, error='User does not have access to this device in ShipChain Profiles')

        modified_http_pretty.assert_calls([{
            'path': f'/api/v1/device/{device.id}/',
            'body': '',
            'host': settings.PROFILES_URL.replace('http://', ''),
        }])

    def test_update_with_device_form_content(self, client_alice, device):
        with mock.patch('apps.shipments.models.Device.get_or_create_with_permission') as mock_device:
            mock_device.return_value = device

            call_count = self.mocked_iot_api.call_count
            self.entity_ref.attributes = None
            self.entity_ref.relationships = [{'device': AssertionHelper.EntityRef(resource='Device', pk=device.id)}]
            device, content_type = create_form_content({'device_id': device.id})

            response = client_alice.patch(self.url, data=device, content_type=content_type)
            AssertionHelper.HTTP_202(response, entity_refs=self.entity_ref)

            mock_device.assert_called()
            self.mocked_iot_api.call_count = call_count + 1

    def test_update_with_device_in_progress(self, client_alice, shipment_alice_with_device):
        with mock.patch('apps.shipments.models.Device.get_or_create_with_permission') as mock_device:
            mock_device.return_value = shipment_alice_with_device.device
            shipment_alice_with_device.pick_up()
            shipment_alice_with_device.save()

            response = client_alice.patch(self.url, data={'device_id': shipment_alice_with_device.device.id})
            AssertionHelper.HTTP_400(response, error='Device is already assigned to a Shipment in progress')

            mock_device.assert_called()

    def test_update_finished_shipment(self, client_alice, shipment_alice_with_device):
        with mock.patch('apps.shipments.models.Device.get_or_create_with_permission') as mock_device:
            mock_device.return_value = shipment_alice_with_device.device
            call_count = self.mocked_iot_api.call_count

            shipment_alice_with_device.pick_up()
            shipment_alice_with_device.save()
            call_count += 1
            assert self.mocked_iot_api.call_count == call_count

            shipment_alice_with_device.arrival()
            shipment_alice_with_device.save()
            call_count += 1
            assert self.mocked_iot_api.call_count == call_count

            shipment_alice_with_device.drop_off()
            shipment_alice_with_device.save()
            call_count += 1
            assert self.mocked_iot_api.call_count == call_count

            self.entity_ref.attributes = None
            self.entity_ref.relationships = [{'device': AssertionHelper.EntityRef(resource='Device', pk=shipment_alice_with_device.device.id)}]

            response = client_alice.patch(self.url, data={'device_id': shipment_alice_with_device.device.id})
            AssertionHelper.HTTP_202(response, entity_refs=self.entity_ref)

            mock_device.assert_called()
            assert self.mocked_iot_api.call_count == call_count + 2

    def test_remove_device(self, client_alice, shipment_alice_with_device):
        call_count = self.mocked_iot_api.call_count
        # Todo: Allow None entity ref to assert empty
        # self.entity_ref.relationships = [{'device': None}]
        self.entity_ref.attributes = None
        self.entity_ref.pk = shipment_alice_with_device.id

        response = client_alice.patch(reverse('shipment-detail', kwargs={'version': 'v1', 'pk': shipment_alice_with_device.id}),
                                      data={'device_id': None})
        AssertionHelper.HTTP_202(response, entity_refs=self.entity_ref)

        assert self.mocked_iot_api.call_count == call_count + 1


class TestShipmentCreate:
    url = reverse('shipment-list', kwargs={'version': 'v1'})

    @pytest.fixture(autouse=True)
    def set_up(self, mocked_engine_rpc, mocked_iot_api, successful_shipment_create_profiles_assertions, profiles_ids):
        self.profiles_ids = profiles_ids
        self.assertions = successful_shipment_create_profiles_assertions
        self.mocked_engine_rpc = mocked_engine_rpc
        self.mocked_iot_api = mocked_iot_api

    def test_requires_authentication(self, api_client):
        response = api_client.post(self.url, data=self.profiles_ids)
        AssertionHelper.HTTP_403(response)

    def test_authenticated_user_can_create(self, client_alice, mock_successful_wallet_owner_calls):
        response = client_alice.post(self.url, data=self.profiles_ids)
        AssertionHelper.HTTP_202(response,
                                 entity_refs=AssertionHelper.EntityRef(
                                     resource='Shipment',
                                     attributes=self.profiles_ids
                                 ))
        assert response.json()['data']['meta']['async_job_id']
        mock_successful_wallet_owner_calls.assert_calls(self.assertions)

        shipment = Shipment.objects.get(id=response.json()['data']['id'])
        assert shipment.background_data_hash_interval == settings.DEFAULT_BACKGROUND_DATA_HASH_INTERVAL
        assert shipment.manual_update_hash_interval == settings.DEFAULT_MANUAL_UPDATE_HASH_INTERVAL

    def test_requires_wallet_ownership(self, client_alice, mock_non_wallet_owner_calls):
        response = client_alice.post(self.url, data=self.profiles_ids)
        # Todo: Assert multiple errors and pointers (wallet/storage_credentials)
        AssertionHelper.HTTP_400(response)
        mock_non_wallet_owner_calls.assert_calls(self.assertions)

    def test_hash_interval_set(self, client_carol, mock_successful_wallet_owner_calls):
        response = client_carol.post(self.url, data=self.profiles_ids)
        AssertionHelper.HTTP_202(response,
                                 entity_refs=AssertionHelper.EntityRef(
                                     resource='Shipment',
                                     attributes=self.profiles_ids
                                 ))
        assert response.json()['data']['meta']['async_job_id']
        mock_successful_wallet_owner_calls.assert_calls(self.assertions)

        shipment = Shipment.objects.get(id=response.json()['data']['id'])
        assert shipment.background_data_hash_interval == 25
        assert shipment.manual_update_hash_interval == 30

    def test_gtx_requires_permisison(self, client_carol, client_gtx_alice, mock_successful_wallet_owner_calls):
        response = client_carol.post(self.url, data={
            'gtx_required': True,
            **self.profiles_ids
        })
        AssertionHelper.HTTP_403(response, error='User does not have access to enable GTX for this shipment')
        mock_successful_wallet_owner_calls.assert_calls(self.assertions)

        response = client_gtx_alice.post(self.url, data={
            'gtx_required': True,
            **self.profiles_ids
        })
        AssertionHelper.HTTP_202(response,
                                 entity_refs=AssertionHelper.EntityRef(
                                     resource='Shipment',
                                     attributes={
                                         'gtx_required': True,
                                         **self.profiles_ids
                                     }
                                 ))
        assert response.json()['data']['meta']['async_job_id']
        mock_successful_wallet_owner_calls.assert_calls(self.assertions)

    def test_cannot_set_asset_physical_id(self, client_alice, mock_successful_wallet_owner_calls):
        response = client_alice.post(self.url, data={
            'asset_physical_id': 'asset_physical_id',
            **self.profiles_ids
        })
        AssertionHelper.HTTP_202(response,
                                 entity_refs=AssertionHelper.EntityRef(
                                     resource='Shipment',
                                     attributes=self.profiles_ids
                                 ))

        mock_successful_wallet_owner_calls.assert_calls(self.assertions)
        shipment = Shipment.objects.get(id=response.json()['data']['id'])

        # Asset Physical Id cannot be set in update
        assert "asset_physical_id" not in response.json()['data']
        assert not shipment.asset_physical_id

    def test_create_with_location_mapbox(self, client_alice, mock_location):
        location_attributes, content_type = create_form_content({
            'ship_from_location.name': "Location Name",
            'ship_from_location.city': "City",
            'ship_from_location.state': "State",
            **self.profiles_ids
        })

        response = client_alice.post(self.url, data=location_attributes, content_type=content_type)

        shipment = Shipment.objects.get(id=response.json()['data']['id'])
        AssertionHelper.HTTP_202(response,
                                 entity_refs=AssertionHelper.EntityRef(
                                     resource='Shipment',
                                     attributes=self.profiles_ids,
                                     relationships=[{
                                         'ship_from_location': AssertionHelper.EntityRef(resource='Location')
                                     }],
                                 ),
                                 included=[AssertionHelper.EntityRef(resource='Location',
                                                                     pk=shipment.ship_from_location.id,
                                                                     attributes={
                                                                         'name': "Location Name",
                                                                         'city': "City",
                                                                         'state': "State",
                                                                         'geometry': {'coordinates': [42.0, 27.0],
                                                                                      'type': 'Point'}
                                                                     })]

                                 )
        mock_location.assert_calls([*self.assertions, {
            'host': 'https://api.mapbox.com',
            'path': '/geocoding/v5/mapbox.places/,%20City,%20State.json',
        }])

    # It is only possible to test location with google OR mapbox due to how the token is gathered by geocoder.
    # We will default to testing with mapbox as that is what is currently used on ShipChain's Transmission services,
    # But this is the test necessary to check the google API call.
    # def test_create_with_location_google(self, client_alice, mock_location):
    #     location_attributes, content_type = create_form_content({
    #         'ship_from_location.name': "Location Name",
    #         'ship_from_location.city': "City",
    #         'ship_from_location.state': "State",
    #         **self.profiles_ids
    #     })
    #
    #     response = client_alice.post(self.url, data=location_attributes, content_type=content_type)
    #
    #     shipment = Shipment.objects.get(id=response.json()['data']['id'])
    #     AssertionHelper.HTTP_202(response,
    #                              entity_refs=AssertionHelper.EntityRef(
    #                                  resource='Shipment',
    #                                  attributes=self.profiles_ids,
    #                                  relationships=[{
    #                                      'ship_from_location': AssertionHelper.EntityRef(resource='Location')
    #                                  }],
    #                              ),
    #                              included=[AssertionHelper.EntityRef(resource='Location',
    #                                                                  pk=shipment.ship_from_location.id,
    #                                                                  attributes={
    #                                                                      'name': "Location Name",
    #                                                                      'city': "City",
    #                                                                      'state': "State",
    #                                                                      'geometry': {'coordinates': [23.0, 12.0],
    #                                                                                   'type': 'Point'}
    #                                                                  })]
    #
    #                              )
    #     mock_location.assert_calls([*self.assertions, {
    #         'host': 'https://maps.googleapis.com',
    #         'path': '/maps/api/geocode/json',
    #         'query': {'address': ', City, State'},
    #     }])

    def test_create_with_multiple_locations(self, client_alice, mock_location):
        location_attributes, content_type = create_form_content({
            'ship_from_location.name': "Location Name",
            'ship_from_location.city': "City",
            'ship_from_location.state': "State",
            'ship_to_location.name': "Location Name",
            'ship_to_location.city': "City",
            'ship_to_location.state': "State",
            **self.profiles_ids
        })

        response = client_alice.post(self.url, data=location_attributes, content_type=content_type)

        shipment = Shipment.objects.get(id=response.json()['data']['id'])
        AssertionHelper.HTTP_202(
            response,
            entity_refs=AssertionHelper.EntityRef(
                resource='Shipment',
                attributes=self.profiles_ids,
                relationships=[
                    {
                        'ship_from_location': AssertionHelper.EntityRef(resource='Location')
                    },
                    {
                        'ship_to_location': AssertionHelper.EntityRef(resource='Location')
                    }
                ],
            ),
            included=[AssertionHelper.EntityRef(resource='Location',
                                                pk=shipment.ship_from_location.id,
                                                attributes={
                                                    'name': "Location Name",
                                                    'city': "City",
                                                    'state': "State",
                                                    'geometry': {'coordinates': [42.0, 27.0], 'type': 'Point'}
                                                }),
                      AssertionHelper.EntityRef(resource='Location',
                                                pk=shipment.ship_to_location.id,
                                                attributes={
                                                    'name': "Location Name",
                                                    'city': "City",
                                                    'state': "State",
                                                    'geometry': {'coordinates': [42.0, 27.0], 'type': 'Point'}
                                                })
                      ]
        )

        mock_location.assert_calls([*self.assertions, {
            'host': 'https://api.mapbox.com',
            'path': '/geocoding/v5/mapbox.places/,%20City,%20State.json',
        }, {
            'host': 'https://api.mapbox.com',
            'path': '/geocoding/v5/mapbox.places/,%20City,%20State.json',
        }])

    def test_create_with_device(self, client_alice, device):
        with mock.patch('apps.shipments.models.Device.get_or_create_with_permission') as mock_device, \
                mock.patch('apps.shipments.serializers.ShipmentCreateSerializer.validate_shipper_wallet_id') as mock_wallet_validation, \
                mock.patch('apps.shipments.serializers.ShipmentCreateSerializer.validate_storage_credentials_id') as mock_storage_validation:
            mock_device.return_value = device
            mock_wallet_validation.return_value = self.profiles_ids['shipper_wallet_id']
            mock_storage_validation.return_value = self.profiles_ids['storage_credentials_id']

            call_count = self.mocked_iot_api.call_count
            response = client_alice.post(self.url, data={
                'device_id': device.id,
                **self.profiles_ids
            })
            AssertionHelper.HTTP_202(response,
                                     entity_refs=AssertionHelper.EntityRef(
                                         resource='Shipment',
                                         attributes=self.profiles_ids,
                                         relationships=[{
                                             'device': AssertionHelper.EntityRef(resource='Device', pk=device.id)
                                         }]
                                     ))

            mock_device.assert_called()
            self.mocked_iot_api.call_count = call_count + 1

    def test_create_with_unavailable_device(self, client_alice, device, mock_successful_wallet_owner_calls):
        mock_successful_wallet_owner_calls.register_uri(mock_successful_wallet_owner_calls.GET,
                                                        f'{settings.PROFILES_URL}/api/v1/device/{device.id}/?is_active',
                                                        status=400)
        response = client_alice.post(self.url, data={
            'device_id': device.id,
            **self.profiles_ids
        })
        AssertionHelper.HTTP_400(response, error='User does not have access to this device in ShipChain Profiles')

        mock_successful_wallet_owner_calls.assert_calls([{
            'path': f'/api/v1/device/{device.id}/',
            'body': '',
            'host': settings.PROFILES_URL.replace('http://', ''),
        }, *self.assertions])

    def test_cannot_create_started_shipment(self, client_alice, shipment_alice_with_device):
        with mock.patch('apps.shipments.models.Device.get_or_create_with_permission') as mock_device, \
                mock.patch('apps.shipments.serializers.ShipmentCreateSerializer.validate_shipper_wallet_id') as mock_wallet_validation, \
                mock.patch('apps.shipments.serializers.ShipmentCreateSerializer.validate_storage_credentials_id') as mock_storage_validation:
            mock_device.return_value = shipment_alice_with_device.device
            mock_wallet_validation.return_value = self.profiles_ids['shipper_wallet_id']
            mock_storage_validation.return_value = self.profiles_ids['storage_credentials_id']
            shipment_alice_with_device.pick_up()
            shipment_alice_with_device.save()
            response = client_alice.post(self.url, data={
                'device_id': shipment_alice_with_device.device.id,
                **self.profiles_ids
            })
            AssertionHelper.HTTP_400(response, error='Device is already assigned to a Shipment in progress')


class TestTrackingRetrieval:
    @pytest.fixture(autouse=True)
    def set_up(self, mocked_engine_rpc, mocked_iot_api, successful_wallet_owner_calls_assertions,
               shipment_alice_with_device, nonsuccessful_wallet_owner_calls_assertions, tracking_data):
        self.assert_success = successful_wallet_owner_calls_assertions
        self.assert_fail = nonsuccessful_wallet_owner_calls_assertions
        self.mocked_iot_api = mocked_iot_api

        self.url = reverse('shipment-tracking', kwargs={'version': 'v1', 'pk': shipment_alice_with_device.id})
        self.url_random = reverse('shipment-tracking', kwargs={'version': 'v1', 'pk': random_id()})
        self.unsigned_tracking = tracking_data
        self.unsigned_tracking['timestamp'] = datetime.utcnow()
        self.unsigned_tracking.update(tracking_data.pop('position'))
        self.shipment = shipment_alice_with_device
        self.add_tracking_data_to_shipment([self.unsigned_tracking], shipment_alice_with_device)

    def add_tracking_data_to_shipment(self, tracking_data, shipment):
        for tracking in tracking_data:
            TrackingData.objects.create(shipment=shipment,
                                        device=shipment.device,
                                        **tracking)

    def test_unauthenticated_user_fails(self, api_client):
        response = api_client.get(self.url)
        AssertionHelper.HTTP_403(response)

    def test_random_shipment_url_fails(self, client_alice):
        response = client_alice.get(self.url_random)
        AssertionHelper.HTTP_404(response)

    def test_empty_shipment_fails(self, client_alice, shipment_alice):
        response = client_alice.get(reverse('shipment-tracking', kwargs={'version': 'v1', 'pk': shipment_alice.id}))
        AssertionHelper.HTTP_404(response, error='No tracking data found for Shipment')
        assert TrackingData.objects.filter(shipment=shipment_alice).count() == 0

    def test_shipment_owner_retrieves(self, client_alice):
        response = client_alice.get(self.url)
        AssertionHelper.HTTP_200(response)
        response_json = response.json()['data']
        assert response_json['type'] == 'FeatureCollection'
        assert response_json['features'][0]['geometry']['type'] == 'Point'
        assert response_json['features'][0]['geometry']['coordinates'] == [self.unsigned_tracking['longitude'], self.unsigned_tracking['latitude']]

    def test_shipment_owner_retrieves_multiple(self, client_alice):
        response = client_alice.get(self.url)
        AssertionHelper.HTTP_200(response)
        response_json = response.json()['data']
        assert response_json['type'] == 'FeatureCollection'
        assert len(response_json['features']) == 1

        tracking_one = deepcopy(self.unsigned_tracking)
        tracking_one['longitude'] += 2
        tracking_one['latitude'] += 2
        tracking_one['timestamp'] += timedelta(minutes=2)

        tracking_two = deepcopy(self.unsigned_tracking)
        tracking_two['longitude'] += 2
        tracking_two['latitude'] += 2
        tracking_two['timestamp'] += timedelta(minutes=4)

        self.add_tracking_data_to_shipment([tracking_one, tracking_two], self.shipment)

        response = client_alice.get(self.url)
        AssertionHelper.HTTP_200(response)
        response_json = response.json()['data']
        assert len(response_json['features']) == 3
        assert response_json['features'][0]['geometry']['coordinates'] == [self.unsigned_tracking['longitude'], self.unsigned_tracking['latitude']]
        assert response_json['features'][2]['geometry']['coordinates'] == [tracking_two['longitude'], tracking_two['latitude']]

    def test_wallet_owner_retrieves(self, client_bob, mock_successful_wallet_owner_calls):
        response = client_bob.get(self.url)
        AssertionHelper.HTTP_200(response)
        response_json = response.json()['data']
        assert response_json['type'] == 'FeatureCollection'
        assert response_json['features'][0]['geometry']['type'] == 'Point'
        assert response_json['features'][0]['geometry']['coordinates'] == [self.unsigned_tracking['longitude'], self.unsigned_tracking['latitude']]
        mock_successful_wallet_owner_calls.assert_calls(self.assert_success)

    def test_non_wallet_owner_fails(self, client_bob, mock_non_wallet_owner_calls):
        response = client_bob.get(self.url)
        AssertionHelper.HTTP_403(response)
        mock_non_wallet_owner_calls.assert_calls(self.assert_fail)

    def test_permission_link(self, api_client, permission_link_device_shipment, permission_link_device_shipment_expired):
        response = api_client.get(f'{self.url}?permission_link={permission_link_device_shipment.id}')
        AssertionHelper.HTTP_200(response)
        response_json = response.json()['data']
        assert response_json['type'] == 'FeatureCollection'
        assert response_json['features'][0]['geometry']['type'] == 'Point'
        assert response_json['features'][0]['geometry']['coordinates'] == [self.unsigned_tracking['longitude'], self.unsigned_tracking['latitude']]

        response = api_client.get(f'{self.url}?permission_link={random_id()}')
        AssertionHelper.HTTP_404(response, error='PermissionLink matching query does not exist.')

        response = api_client.get(f'{self.url}?permission_link={permission_link_device_shipment_expired.id}')
        AssertionHelper.HTTP_403(response)
