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

import random
import datetime

import pytest
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
def shipments_with_device(user_alice, user_bob, devices, mocked_engine_rpc, mocked_iot_api):
    list_shipment = []
    owner_id = user_alice.token.payload['organization_id']
    third_owner_id = user_bob.token.payload['organization_id']

    for device in devices:
        list_shipment.append(Shipment.objects.create(vault_id=random_id(),
                                                     carrier_wallet_id=random_id(),
                                                     shipper_wallet_id=random_id(),
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
    for shipment in shipments_with_device:
        device = shipment.device
        if device:
            for in_bbox_data in tracking_data[0]:
                in_bbox_data['device'] = device
                in_bbox_data['shipment'] = shipment
                TrackingData.objects.create(**in_bbox_data)

    # One shipment with tracking data outside of Bbox
    shipment = shipments_with_device[NUM_DEVICES-1]
    device = shipment.device
    for out_of_bbox_data in tracking_data[1]:
        out_of_bbox_data['timestamp'] = datetime.datetime.utcnow()
        out_of_bbox_data['device'] = device
        out_of_bbox_data['shipment'] = shipment
        TrackingData.objects.create(**out_of_bbox_data)

    return shipments_with_device


@pytest.mark.django_db
def test_owner_shipment_device_location(client_alice, api_client, shipment_tracking_data):
    url = reverse('shipments-overview', kwargs={'version': 'v1'})

    # An unauthenticated request should with 403 status code
    response = api_client.get(url)
    AssertionHelper.HTTP_403(response)

    # An authenticated user can list only the shipments
    # he owns with reported tracking data. In this case exactly (NUM_DEVICES - 2)
    response = client_alice.get(url)
    response_data = response.json()
    AssertionHelper.HTTP_200(response, vnd=True, is_list=True)
    assert response_data['meta']['pagination']['count'] == NUM_DEVICES - 2
    assert len(response_data['included']) == NUM_DEVICES - 2


@pytest.mark.django_db
def test_filter_shipment_device_location(client_alice, shipment_tracking_data, json_asserter):
    url = reverse('shipments-overview', kwargs={'version': 'v1'})

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

    in_transit_url = f'{url}?state={TransitState.IN_TRANSIT.name.lower()}'

    # There is exactly one shipment in transit state
    response = client_alice.get(in_transit_url)
    response_data = response.json()
    AssertionHelper.HTTP_200(response, vnd=True, is_list=True)
    assert response_data['meta']['pagination']['count'] == 1

    list_state_url = f'{url}?state={TransitState.IN_TRANSIT.name.lower()}&state={TransitState.AWAITING_DELIVERY.name}'

    # There is exactly one shipment in transit state and one in awaiting delivery
    response = client_alice.get(list_state_url)
    response_data = response.json()
    AssertionHelper.HTTP_200(response, vnd=True, is_list=True)
    assert response_data['meta']['pagination']['count'] == 2

    has_location_url = f'{url}?has_ship_to_location=true'

    # There is exactly one shipment with the field ship_to_location populated
    response = client_alice.get(has_location_url)
    response_data = response.json()
    AssertionHelper.HTTP_200(response, vnd=True, is_list=True)
    assert response_data['meta']['pagination']['count'] == 1

    search_url = f'{url}?search=greenville'

    # There is exactly one shipment with the word `greenville` located on field ship_to_location.city
    response = client_alice.get(search_url)
    response_data = response.json()
    AssertionHelper.HTTP_200(response, vnd=True, is_list=True)
    assert response_data['meta']['pagination']['count'] == 1

    search_url = f'{url}?search=purposes'

    # There is exactly one shipment with the word `purposes` located on field shippers_reference
    response = client_alice.get(search_url)
    response_data = response.json()
    AssertionHelper.HTTP_200(response, vnd=True, is_list=True)
    assert response_data['meta']['pagination']['count'] == 1

    search_url = f'{url}?search=Infinity'

    # There isn't any shipment with reference of word `Infinity`
    response = client_alice.get(search_url)
    response_data = response.json()
    AssertionHelper.HTTP_200(response, vnd=True, is_list=True)
    assert response_data['meta']['pagination']['count'] == 0


@pytest.mark.django_db
def test_bbox_param(client_alice, shipment_tracking_data):
    url = reverse('shipments-overview', kwargs={'version': 'v1'})

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
