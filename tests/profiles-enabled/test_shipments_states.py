#  Copyright 2019 ShipChain, Inc.
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
from datetime import datetime
import hashlib

import pytest
import pytz
from dateutil.parser import parse as dt_parse
from dateutil.relativedelta import relativedelta
from rest_framework import status
from rest_framework.reverse import reverse
from shipchain_common.test_utils import datetimeAlmostEqual

from apps.shipments.models import TransitState
from apps.shipments.serializers import ActionType


@pytest.mark.django_db
def test_protected_shipment_date_updates(api_client, shipment):
    url = reverse('shipment-detail', kwargs={'version': 'v1', 'pk': shipment.id})

    start_date = datetime.utcnow().replace(tzinfo=pytz.UTC) - relativedelta(years=1)
    parameters = {
        'pickup_est': start_date.isoformat(),
        'pickup_act': (start_date + relativedelta(days=1)).isoformat(),
        'port_arrival_est': (start_date + relativedelta(days=2)).isoformat(),
        'port_arrival_act': (start_date + relativedelta(days=3)).isoformat(),
        'delivery_est': (start_date + relativedelta(days=4)).isoformat(),
        'delivery_act': (start_date + relativedelta(days=5)).isoformat(),
    }
    # Assert that none of the values to be updated already exist
    for field in parameters:
        assert getattr(shipment, field) != parameters[field], f'Field: {field}'

    response = api_client.patch(url, data=parameters, format='json')
    assert response.status_code == status.HTTP_202_ACCEPTED
    updated_parameters = response.json()['data']['attributes']

    # Assert that only the updatable fields got updated
    for field in parameters:
        if '_act' in field:
            assert updated_parameters[field] is None, f'Field: {field}'
        else:
            assert dt_parse(parameters[field]) == dt_parse(updated_parameters[field]), f'Field: {field}'


@pytest.mark.django_db
def test_pickup(api_client, shipment):
    assert shipment.pickup_act is None
    url = reverse('shipment-actions', kwargs={'version': 'v1', 'shipment_pk': shipment.id})
    action = {
        'action_type': ActionType.PICK_UP.name
    }

    response = api_client.post(url, data=action, format='json')
    assert response.status_code == status.HTTP_200_OK

    updated_parameters = response.json()['data']['attributes']

    assert updated_parameters['state'] == TransitState.IN_TRANSIT.name
    assert datetimeAlmostEqual(dt_parse(updated_parameters['pickup_act']))

    # Can't pickup when IN_TRANSIT
    response = api_client.post(url, data=action, format='json')
    assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_arrival(api_client, shipment):
    assert shipment.port_arrival_act is None
    url = reverse('shipment-actions', kwargs={'version': 'v1', 'shipment_pk': shipment.id})
    action = {
        'action_type': ActionType.ARRIVAL.name
    }

    response = api_client.post(url, data=action, format='json')
    assert response.status_code == status.HTTP_400_BAD_REQUEST  # Can't go from AWAITING_PICKUP -> AWAITING_DELIVERY
    shipment.pick_up()
    shipment.save()

    response = api_client.post(url, data=action, format='json')
    assert response.status_code == status.HTTP_200_OK

    updated_parameters = response.json()['data']['attributes']

    assert updated_parameters['state'] == TransitState.AWAITING_DELIVERY.name
    assert datetimeAlmostEqual(dt_parse(updated_parameters['port_arrival_act']))

    # Can't pickup or arrive when AWAITING_DELIVERY
    response = api_client.post(url, data=action, format='json')
    assert response.status_code == status.HTTP_400_BAD_REQUEST

    action = {
        'action_type': ActionType.PICK_UP.name
    }
    response = api_client.post(url, data=action, format='json')
    assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_dropoff(api_client, shipment):
    assert shipment.delivery_act is None
    url = reverse('shipment-actions', kwargs={'version': 'v1', 'shipment_pk': shipment.id})
    action = {
        'action_type': ActionType.DROP_OFF.name
    }

    response = api_client.post(url, data=action, format='json')
    assert response.status_code == status.HTTP_400_BAD_REQUEST  # Can't go from AWAITING_PICKUP -> DELIVERED
    shipment.pick_up()
    shipment.save()

    response = api_client.post(url, data=action, format='json')
    assert response.status_code == status.HTTP_400_BAD_REQUEST  # Can't go from IN_TRANSIT -> DELIVERED
    shipment.arrival()
    shipment.save()

    response = api_client.post(url, data=action, format='json')
    assert response.status_code == status.HTTP_200_OK

    updated_parameters = response.json()['data']['attributes']
    assert updated_parameters['state'] == TransitState.DELIVERED.name
    assert datetimeAlmostEqual(dt_parse(updated_parameters['delivery_act']))

    # Can't pickup/arrive/deliver when DELIVERED
    response = api_client.post(url, data=action, format='json')
    assert response.status_code == status.HTTP_400_BAD_REQUEST

    action = {
        'action_type': ActionType.PICK_UP.name
    }
    response = api_client.post(url, data=action, format='json')
    assert response.status_code == status.HTTP_400_BAD_REQUEST

    action = {
        'action_type': ActionType.ARRIVAL.name
    }
    response = api_client.post(url, data=action, format='json')
    assert response.status_code == status.HTTP_400_BAD_REQUEST

    action = {
        'action_type': ActionType.DROP_OFF.name
    }
    response = api_client.post(url, data=action, format='json')
    assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_readonly_state(api_client, shipment):
    assert TransitState(shipment.state) == TransitState.AWAITING_PICKUP

    with pytest.raises(AttributeError):
        shipment.state = TransitState.IN_TRANSIT
    shipment.save()

    assert TransitState(shipment.state) == TransitState.AWAITING_PICKUP


@pytest.mark.django_db
def test_shadow_state_updates(api_client, mocked_iot_api, shipment_with_device):
    call_count = mocked_iot_api.call_count
    shipment_with_device.pick_up()
    shipment_with_device.save()
    call_count += 1  # Status should have been updated in the shadow
    assert call_count == mocked_iot_api.call_count


@pytest.mark.django_db
def test_dropoff_gtx(api_client, shipment):
    assert shipment.delivery_act is None

    # Set NFC/Asset ID
    super_secret_nfc_id = 'package123'
    shipment.asset_physical_id = hashlib.sha256(super_secret_nfc_id.encode()).hexdigest()
    shipment.save()

    shipment.pick_up()
    shipment.save()

    shipment.arrival()
    shipment.save()

    url = reverse('shipment-actions', kwargs={'version': 'v1', 'shipment_pk': shipment.id})
    action = {
        'action_type': ActionType.DROP_OFF.name
    }

    response = api_client.post(url, data=action, format='json')
    assert response.status_code == status.HTTP_403_FORBIDDEN  # No asset ID

    action['raw_asset_physical_id'] = 'package987'

    response = api_client.post(url, data=action, format='json')
    assert response.status_code == status.HTTP_403_FORBIDDEN  # Invalid asset ID

    action['raw_asset_physical_id'] = super_secret_nfc_id

    response = api_client.post(url, data=action, format='json')
    assert response.status_code == status.HTTP_200_OK
