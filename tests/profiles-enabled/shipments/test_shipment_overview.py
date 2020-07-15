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

import datetime
import json

import pytest
import random
from django.conf import settings
from rest_framework import status
from rest_framework.reverse import reverse
from shipchain_common.test_utils import AssertionHelper
from shipchain_common.utils import random_id

from apps.shipments.models import Shipment, Device, Location, TrackingData, TransitState
from apps.shipments.serializers import ActionType

BBOX = [-90.90, 30.90, -78.80, 36.80]

NUM_DEVICES = 7     # should be >= 7
NUM_TRACKING_DATA_BBOX = 3

OWNER_ID = random_id()
THIRD_OWNER_ID = random_id()


@pytest.fixture
def devices():
    list_device = []
    for i in range(0, NUM_DEVICES):
        list_device.append(Device.objects.create(id=random_id()))

    return list_device


@pytest.fixture
def shipments_with_device(user_alice, user_bob, devices, mocked_engine_rpc, mocked_iot_api, profiles_ids):
    list_shipment = []
    owner_id = user_alice.token.payload['organization_id']
    third_owner_id = user_bob.token.payload['organization_id']

    for device in devices:
        list_shipment.append(Shipment.objects.create(vault_id=random_id(),
                                                     carrier_wallet_id=profiles_ids['carrier_wallet_id'],
                                                     shipper_wallet_id=profiles_ids['shipper_wallet_id'],
                                                     storage_credentials_id=random_id(),
                                                     device=device,
                                                     owner_id=owner_id))

    # Shipment without device
    list_shipment[NUM_DEVICES-2].device_id = None

    # Shipment not owned
    list_shipment[NUM_DEVICES-3].owner_id = third_owner_id

    # Shipment with location field populated
    location = Location.objects.create(name='Test Location', city='Greenville')
    list_shipment[NUM_DEVICES-4].ship_to_location = location

    # Shipment with shipper's reference field populated
    list_shipment[NUM_DEVICES-5].shippers_reference = 'For search purposes'

    for shipment in list_shipment:
        shipment.save()

    return list_shipment


@pytest.fixture
def tracking_data():
    in_bbox, out_of_bbox = [], []
    for i in range(0, NUM_TRACKING_DATA_BBOX):
        in_bbox.append(
            {
                'latitude': random.uniform(BBOX[1], BBOX[3]),
                'longitude': random.uniform(BBOX[0], BBOX[2]),
                'source': 'GPS',
                'timestamp': datetime.datetime.utcnow(),
                'version': '1.1.0'
            }
        )

        out_of_bbox.append(
            {
                'latitude': random.uniform(BBOX[1], BBOX[3]),
                'longitude': random.uniform(BBOX[1], BBOX[3]),
                'source': 'GPS',
                'timestamp': datetime.datetime.utcnow(),
                'version': '1.1.0'
            }
        )

    return in_bbox, out_of_bbox


@pytest.fixture
def shipment_tracking_data(shipments_with_device, tracking_data):
    shipments_with_tracking = []
    for shipment in shipments_with_device:
        device = shipment.device
        if device:
            for in_bbox_data in tracking_data[0]:
                in_bbox_data['device'] = device
                in_bbox_data['shipment'] = shipment
                TrackingData.objects.create(**in_bbox_data)
            shipments_with_tracking.append(shipment)

    # One shipment with tracking data outside of Bbox
    shipment = shipments_with_device[NUM_DEVICES-1]
    device = shipment.device
    for out_of_bbox_data in tracking_data[1]:
        out_of_bbox_data['timestamp'] = datetime.datetime.utcnow() + datetime.timedelta(seconds=1)
        out_of_bbox_data['device'] = device
        out_of_bbox_data['shipment'] = shipment
        TrackingData.objects.create(**out_of_bbox_data)

    return shipments_with_tracking


@pytest.mark.django_db
def test_owner_shipment_device_location(client_alice, api_client, shipment_tracking_data, mocked_profiles_wallet_list,
                                        profiles_wallet_list_assertions):
    url = reverse('shipment-overview', kwargs={'version': 'v1'})

    # An unauthenticated request should with 403 status code
    response = api_client.get(url)
    AssertionHelper.HTTP_403(response)

    # An authenticated user can list only the shipments
    # he owns with reported tracking data. In this case exactly (NUM_DEVICES - 2)
    response = client_alice.get(url)
    response_data = response.json()
    AssertionHelper.HTTP_200(response, vnd=True, is_list=True, count=len(shipment_tracking_data) - 1)
    assert len(response_data['included']) == NUM_DEVICES - 2
    mocked_profiles_wallet_list.assert_calls(profiles_wallet_list_assertions)


@pytest.mark.django_db
def test_wallet_owner_retrieval(client_bob, api_client, shipment_tracking_data, modified_http_pretty, profiles_ids,
                                profiles_wallet_list_assertions):
    modified_http_pretty.register_uri(modified_http_pretty.GET,
                                      f"{settings.PROFILES_URL}/api/v1/wallet",
                                      body=json.dumps({'data': []}), status=status.HTTP_200_OK)
    url = reverse('shipment-overview', kwargs={'version': 'v1'})

    response = client_bob.get(url)
    AssertionHelper.HTTP_200(response, vnd=True, is_list=True, count=1)
    modified_http_pretty.assert_calls(profiles_wallet_list_assertions)

    modified_http_pretty.register_uri(modified_http_pretty.GET,
                                      f"{settings.PROFILES_URL}/api/v1/wallet",
                                      body=json.dumps({'data': [
                                          {'id': profiles_ids['carrier_wallet_id']},
                                          {'id': profiles_ids['shipper_wallet_id']},
                                      ]}), status=status.HTTP_200_OK)

    response = client_bob.get(url)
    AssertionHelper.HTTP_200(response, vnd=True, is_list=True, count=len(shipment_tracking_data))
    assert len(response.json()['included']) == NUM_DEVICES - 1
    modified_http_pretty.assert_calls(profiles_wallet_list_assertions)


def test_ordering(client_alice, api_client, shipment_tracking_data, mocked_profiles_wallet_list,
                  profiles_wallet_list_assertions):
    url = reverse('shipment-overview', kwargs={'version': 'v1'})

    response = client_alice.get(f'{url}?ordering=-created_at')
    AssertionHelper.HTTP_200(response, vnd=True, is_list=True, check_ordering=True,
                             entity_refs=[AssertionHelper.EntityRef(
                                 resource='TrackingData',
                                 relationships=[{
                                     'shipment': AssertionHelper.EntityRef(
                                         resource='Shipment',
                                         pk=shipment_tracking_data[5].id
                                     )
                                 }]
                             ), AssertionHelper.EntityRef(
                                 resource='TrackingData',
                                 relationships=[{
                                     'shipment': AssertionHelper.EntityRef(
                                         resource='Shipment',
                                         pk=shipment_tracking_data[3].id
                                     )
                                 }]
                             ), AssertionHelper.EntityRef(
                                 resource='TrackingData',
                                 relationships=[{
                                     'shipment': AssertionHelper.EntityRef(
                                         resource='Shipment',
                                         pk=shipment_tracking_data[2].id
                                     )
                                 }]
                             ), AssertionHelper.EntityRef(
                                 resource='TrackingData',
                                 relationships=[{
                                     'shipment': AssertionHelper.EntityRef(
                                         resource='Shipment',
                                         pk=shipment_tracking_data[1].id
                                     )
                                 }]
                             ), AssertionHelper.EntityRef(
                                 resource='TrackingData',
                                 relationships=[{
                                     'shipment': AssertionHelper.EntityRef(
                                         resource='Shipment',
                                         pk=shipment_tracking_data[0].id
                                     )
                                 }]
                             )])
    mocked_profiles_wallet_list.assert_calls(profiles_wallet_list_assertions)

    response = client_alice.get(f'{url}?ordering=created_at')
    AssertionHelper.HTTP_200(response, vnd=True, is_list=True, check_ordering=True,
                             entity_refs=[AssertionHelper.EntityRef(
                                 resource='TrackingData',
                                 relationships=[{
                                     'shipment': AssertionHelper.EntityRef(
                                         resource='Shipment',
                                         pk=shipment_tracking_data[0].id
                                     )
                                 }]
                             ), AssertionHelper.EntityRef(
                                 resource='TrackingData',
                                 relationships=[{
                                     'shipment': AssertionHelper.EntityRef(
                                         resource='Shipment',
                                         pk=shipment_tracking_data[1].id
                                     )
                                 }]
                             ), AssertionHelper.EntityRef(
                                 resource='TrackingData',
                                 relationships=[{
                                     'shipment': AssertionHelper.EntityRef(
                                         resource='Shipment',
                                         pk=shipment_tracking_data[2].id
                                     )
                                 }]
                             ), AssertionHelper.EntityRef(
                                 resource='TrackingData',
                                 relationships=[{
                                     'shipment': AssertionHelper.EntityRef(
                                         resource='Shipment',
                                         pk=shipment_tracking_data[3].id
                                     )
                                 }]
                             ), AssertionHelper.EntityRef(
                                 resource='TrackingData',
                                 relationships=[{
                                     'shipment': AssertionHelper.EntityRef(
                                         resource='Shipment',
                                         pk=shipment_tracking_data[5].id
                                     )
                                 }]
                             )])
    mocked_profiles_wallet_list.assert_calls(profiles_wallet_list_assertions)


def test_search_custom_fields(client_alice, shipment_tracking_data, mocked_profiles_wallet_list,
                              profiles_wallet_list_assertions):
    url = reverse('shipment-overview', kwargs={'version': 'v1'})
    customer_fields = {
        'number': 8675309,
        'boolean': True,
        'datetime': datetime.datetime.utcnow().isoformat(),
        'decimal': 3.14,
        'string': 'value'
    }
    shipment_tracking_data[0].customer_fields = customer_fields
    shipment_tracking_data[0].save()
    for value in customer_fields.values():
        response = client_alice.get(f'{url}?search={json.dumps(value)}')
        AssertionHelper.HTTP_200(response, vnd=True, is_list=True, check_ordering=True,
                                 entity_refs=[AssertionHelper.EntityRef(
                                     resource='TrackingData',
                                     relationships=[{
                                         'shipment': AssertionHelper.EntityRef(
                                             resource='Shipment',
                                             pk=shipment_tracking_data[0].id
                                         )
                                     }]
                                 )])
        mocked_profiles_wallet_list.assert_calls(profiles_wallet_list_assertions)


def test_filter_custom_fields(client_alice, shipment_tracking_data, mocked_profiles_wallet_list,
                              profiles_wallet_list_assertions):
    url = reverse('shipment-overview', kwargs={'version': 'v1'})
    customer_fields = {
        'number': 8675309,
        'boolean': True,
        'datetime': datetime.datetime.utcnow().isoformat(),
        'decimal': 3.14,
        'string': 'value'
    }
    shipment_tracking_data[0].customer_fields = customer_fields
    shipment_tracking_data[0].save()
    for key, value in customer_fields.items():
        response = client_alice.get(f'{url}?customer_fields__{key}={json.dumps(value)}')
        AssertionHelper.HTTP_200(response, vnd=True, is_list=True, count=1,
                                 entity_refs=[AssertionHelper.EntityRef(
                                     resource='TrackingData',
                                     relationships=[{
                                         'shipment': AssertionHelper.EntityRef(
                                             resource='Shipment',
                                             pk=shipment_tracking_data[0].id
                                         )
                                     }]
                                 )])
        mocked_profiles_wallet_list.assert_calls(profiles_wallet_list_assertions)


@pytest.mark.django_db
def test_filter_shipment_device_location(client_alice, shipment_tracking_data, mocked_profiles_wallet_list,
                                         profiles_wallet_list_assertions):
    url = reverse('shipment-overview', kwargs={'version': 'v1'})

    shipment_action_url = reverse('shipment-actions',
                                  kwargs={'version': 'v1', 'shipment_pk': shipment_tracking_data[0].id})

    shipment2_action_url = reverse('shipment-actions',
                                   kwargs={'version': 'v1', 'shipment_pk': shipment_tracking_data[1].id})

    pickup_action = {
        'action_type': ActionType.PICK_UP.name
    }

    arrival_action = {
        'action_type': ActionType.ARRIVAL.name
    }

    # One shipment in `IN_TRANSIT` state and one in `AWAITING_DELIVERY`
    action_response = client_alice.post(shipment_action_url, data=pickup_action)
    AssertionHelper.HTTP_200(action_response)

    action_response = client_alice.post(shipment2_action_url, data=pickup_action)
    AssertionHelper.HTTP_200(action_response)

    action_response = client_alice.post(shipment2_action_url, data=arrival_action)
    AssertionHelper.HTTP_200(action_response)

    in_bbox_url = f'{url}?in_bbox={",".join([str(x) for x in BBOX])}'

    # The primary user has exactly (NUM_DEVICES - 3) inside Bbox
    response = client_alice.get(in_bbox_url)
    response_data = response.json()
    AssertionHelper.HTTP_200(response, vnd=True, is_list=True)
    assert response_data['meta']['pagination']['count'] == NUM_DEVICES - 3
    mocked_profiles_wallet_list.assert_calls(profiles_wallet_list_assertions)

    in_transit_url = f'{url}?state={TransitState.IN_TRANSIT.name.lower()}'

    # There is exactly one shipment in transit state
    response = client_alice.get(in_transit_url)
    response_data = response.json()
    AssertionHelper.HTTP_200(response, vnd=True, is_list=True)
    assert response_data['meta']['pagination']['count'] == 1
    mocked_profiles_wallet_list.assert_calls(profiles_wallet_list_assertions)

    list_state_url = f'{url}?state={TransitState.IN_TRANSIT.name.lower()}&state={TransitState.AWAITING_DELIVERY.name}'

    # There is exactly one shipment in transit state and one in awaiting delivery
    response = client_alice.get(list_state_url)
    response_data = response.json()
    AssertionHelper.HTTP_200(response, vnd=True, is_list=True)
    assert response_data['meta']['pagination']['count'] == 2
    mocked_profiles_wallet_list.assert_calls(profiles_wallet_list_assertions)

    has_location_url = f'{url}?has_ship_to_location=true'

    # There is exactly one shipment with the field ship_to_location populated
    response = client_alice.get(has_location_url)
    response_data = response.json()
    AssertionHelper.HTTP_200(response, vnd=True, is_list=True)
    assert response_data['meta']['pagination']['count'] == 1
    mocked_profiles_wallet_list.assert_calls(profiles_wallet_list_assertions)

    search_url = f'{url}?search=greenville'

    # There is exactly one shipment with the word `greenville` located on field ship_to_location.city
    response = client_alice.get(search_url)
    response_data = response.json()
    AssertionHelper.HTTP_200(response, vnd=True, is_list=True)
    assert response_data['meta']['pagination']['count'] == 1
    mocked_profiles_wallet_list.assert_calls(profiles_wallet_list_assertions)

    search_url = f'{url}?search=purposes'

    # There is exactly one shipment with the word `purposes` located on field shippers_reference
    response = client_alice.get(search_url)
    response_data = response.json()
    AssertionHelper.HTTP_200(response, vnd=True, is_list=True)
    assert response_data['meta']['pagination']['count'] == 1
    mocked_profiles_wallet_list.assert_calls(profiles_wallet_list_assertions)

    search_url = f'{url}?search=Infinity'

    # There isn't any shipment with reference of word `Infinity`
    response = client_alice.get(search_url)
    response_data = response.json()
    AssertionHelper.HTTP_200(response, vnd=True, is_list=True)
    assert response_data['meta']['pagination']['count'] == 0
    mocked_profiles_wallet_list.assert_calls(profiles_wallet_list_assertions)


@pytest.mark.django_db
def test_bbox_param(client_alice, shipment_tracking_data, mocked_profiles_wallet_list, profiles_wallet_list_assertions):
    url = reverse('shipment-overview', kwargs={'version': 'v1'})

    bbox_reversed = BBOX.copy()
    bbox_reversed.reverse()
    bad_in_bbox_url_1 = f'{url}?in_bbox={",".join([str(x) for x in bbox_reversed])}'

    bad_in_bbox_url_2 = f'{url}?in_bbox={",".join([str(x) for x in BBOX[0:2]])}'

    good_in_bbox_url = f'{url}?in_bbox={",".join([str(x) for x in BBOX])}'

    response = client_alice.get(bad_in_bbox_url_1)
    AssertionHelper.HTTP_400(response)

    response = client_alice.get(bad_in_bbox_url_2)
    AssertionHelper.HTTP_400(response)

    response = client_alice.get(good_in_bbox_url)
    AssertionHelper.HTTP_200(response, vnd=True, is_list=True)
    mocked_profiles_wallet_list.assert_calls(profiles_wallet_list_assertions)


@pytest.mark.django_db
def test_latest_tracking(client_alice, tracking_data, shipment_tracking_data, mocked_profiles_wallet_list,
                         profiles_wallet_list_assertions):
    shipment = shipment_tracking_data[0]
    data_point = TrackingData(**tracking_data[0][0])
    data_point.shipment = shipment
    data_point.device = shipment.device
    data_point.timestamp = datetime.datetime.utcnow() + datetime.timedelta(days=1)
    data_point.save()
    url = reverse('shipment-overview', kwargs={'version': 'v1'})
    response = client_alice.get(url)

    # Ensure that 'latest' tracking data is included in the response
    AssertionHelper.HTTP_200(response, vnd=True, is_list=True,
                             entity_refs=AssertionHelper.EntityRef(
                                 resource='TrackingData',
                                 pk=data_point.id,
                                 attributes={'point': {
                                     'type': 'Feature',
                                     'geometry': {
                                         'type': 'Point',
                                         'coordinates': [data_point.point.x, data_point.point.y]
                                     },
                                     'properties': {
                                         'source': data_point.source,
                                         'uncertainty': data_point.uncertainty,
                                         'time': f'{data_point.timestamp.isoformat()}Z'
                                    }
                                 }}
                             ))
    mocked_profiles_wallet_list.assert_calls(profiles_wallet_list_assertions)
