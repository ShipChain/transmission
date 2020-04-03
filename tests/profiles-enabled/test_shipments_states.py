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
import hashlib
from datetime import datetime

import pytest
import pytz
from dateutil.parser import parse as dt_parse
from dateutil.relativedelta import relativedelta
from rest_framework import status
from rest_framework.reverse import reverse
from shipchain_common.test_utils import datetimeAlmostEqual, AssertionHelper, modified_http_pretty

from django.conf import settings
from apps.shipments.models import TransitState, GTXValidation
from apps.shipments.serializers import ActionType


@pytest.fixture
def gtx_validation_assertion(shipment):
    return [{"host": settings.GTX_VALIDATION_URL.replace('/validate', ''),
             "path": "/validate",
             "body": {"shipment_id": shipment.id,
                      "asset_physical_id": hashlib.sha256('nfc_tag'.encode()).hexdigest()}}]


@pytest.mark.django_db
def test_protected_shipment_date_updates(client_alice, shipment):
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

    response = client_alice.patch(url, data=parameters)
    AssertionHelper.HTTP_202(response,
                             entity_refs=AssertionHelper.EntityRef(
                                 resource='Shipment',
                                 pk=shipment.id,
                             ))
    updated_parameters = response.json()['data']['attributes']

    # Assert that only the updatable fields got updated
    for field in parameters:
        if '_act' in field:
            assert updated_parameters[field] is None, f'Field: {field}'
        else:
            assert dt_parse(parameters[field]) == dt_parse(updated_parameters[field]), f'Field: {field}'


@pytest.mark.django_db
def test_pickup(client_alice, shipment):
    assert shipment.pickup_act is None
    url = reverse('shipment-actions', kwargs={'version': 'v1', 'shipment_pk': shipment.id})
    action = {
        'action_type': ActionType.PICK_UP.name
    }

    response = client_alice.post(url, data=action)
    AssertionHelper.HTTP_200(response,
                             entity_refs=AssertionHelper.EntityRef(
                                 resource='Shipment',
                                 pk=shipment.id,
                                 attributes={'state': TransitState.IN_TRANSIT.name}
                             ))

    updated_parameters = response.json()['data']['attributes']

    assert datetimeAlmostEqual(dt_parse(updated_parameters['pickup_act']))

    # Can't pickup when IN_TRANSIT
    response = client_alice.post(url, data=action)
    AssertionHelper.HTTP_400(response, error='Action PICK_UP not available while Shipment is in state IN_TRANSIT',
                             pointer='action_type')


@pytest.mark.django_db
def test_pickup_with_gtx_required(client_alice, shipment, modified_http_pretty, gtx_validation_assertion):
    modified_http_pretty.register_uri(modified_http_pretty.POST, settings.GTX_VALIDATION_URL)

    assert shipment.pickup_act is None
    shipment.gtx_required = True
    shipment.save()

    url = reverse('shipment-actions', kwargs={'version': 'v1', 'shipment_pk': shipment.id})

    action = {
        'action_type': ActionType.PICK_UP.name
    }

    # If gtx_required, pickup requires an asset_physical_id
    response = client_alice.post(url, data=action)
    AssertionHelper.HTTP_403(response, error='In order to proceed with this shipment pick up, you need to provide a '
                                             'value for the field [Shipment.asset_physical_id]')

    action['asset_physical_id'] = 'nfc_tag'
    response = client_alice.post(url, data=action)
    AssertionHelper.HTTP_200(response,
                             entity_refs=AssertionHelper.EntityRef(
                                 resource='Shipment',
                                 pk=shipment.id,
                                 attributes={'state': TransitState.IN_TRANSIT.name,
                                             'gtx_validation': GTXValidation.VALIDATED.name})
                             )

    modified_http_pretty.assert_calls(gtx_validation_assertion)


@pytest.mark.django_db
def test_pickup_doesnt_require_gtx(client_alice, shipment, modified_http_pretty, gtx_validation_assertion):
    modified_http_pretty.register_uri(modified_http_pretty.POST, settings.GTX_VALIDATION_URL,
                                      status=status.HTTP_403_FORBIDDEN)

    assert shipment.pickup_act is None
    shipment.gtx_required = True
    shipment.save()

    url = reverse('shipment-actions', kwargs={'version': 'v1', 'shipment_pk': shipment.id})

    action = {
        'action_type': ActionType.PICK_UP.name
    }

    # If gtx_required, pickup requires an asset_physical_id
    response = client_alice.post(url, data=action)
    AssertionHelper.HTTP_403(response, error='In order to proceed with this shipment pick up, you need to provide a '
                                             'value for the field [Shipment.asset_physical_id]')

    action['asset_physical_id'] = 'nfc_tag'
    response = client_alice.post(url, data=action)
    AssertionHelper.HTTP_200(response,
                             entity_refs=AssertionHelper.EntityRef(
                                 resource='Shipment',
                                 pk=shipment.id,
                                 attributes={'state': TransitState.IN_TRANSIT.name,
                                             'gtx_validation': GTXValidation.VALIDATION_FAILED.name})
                             )

    modified_http_pretty.assert_calls(gtx_validation_assertion)


@pytest.mark.django_db
def test_arrival(client_alice, shipment):
    assert shipment.port_arrival_act is None
    url = reverse('shipment-actions', kwargs={'version': 'v1', 'shipment_pk': shipment.id})
    action = {
        'action_type': ActionType.ARRIVAL.name
    }

    response = client_alice.post(url, data=action)
    AssertionHelper.HTTP_400(response,
                             error='Action ARRIVAL not available while Shipment is in state AWAITING_PICKUP',
                             pointer='action_type')
    shipment.pick_up()
    shipment.save()

    response = client_alice.post(url, data=action)
    AssertionHelper.HTTP_200(response,
                             entity_refs=AssertionHelper.EntityRef(
                                 resource='Shipment',
                                 pk=shipment.id,
                                 attributes={'state': TransitState.AWAITING_DELIVERY.name})
                             )

    updated_parameters = response.json()['data']['attributes']

    assert datetimeAlmostEqual(dt_parse(updated_parameters['port_arrival_act']))

    # Can't pickup or arrive when AWAITING_DELIVERY
    response = client_alice.post(url, data=action)
    AssertionHelper.HTTP_400(response,
                             error='Action ARRIVAL not available while Shipment is in state AWAITING_DELIVERY',
                             pointer='action_type')

    action = {
        'action_type': ActionType.PICK_UP.name
    }
    response = client_alice.post(url, data=action)
    AssertionHelper.HTTP_400(response,
                             error='Action PICK_UP not available while Shipment is in state AWAITING_DELIVERY',
                             pointer='action_type')


@pytest.mark.django_db
def test_dropoff(client_alice, shipment):
    assert shipment.delivery_act is None
    url = reverse('shipment-actions', kwargs={'version': 'v1', 'shipment_pk': shipment.id})
    action = {
        'action_type': ActionType.DROP_OFF.name
    }

    response = client_alice.post(url, data=action)
    AssertionHelper.HTTP_400(response,
                             error='Action DROP_OFF not available while Shipment is in state AWAITING_PICKUP',
                             pointer='action_type')
    # Can't go from AWAITING_PICKUP -> DELIVERED
    shipment.pick_up()
    shipment.save()

    response = client_alice.post(url, data=action)
    AssertionHelper.HTTP_400(response,
                             error='Action DROP_OFF not available while Shipment is in state IN_TRANSIT',
                             pointer='action_type')  # Can't go from IN_TRANSIT -> DELIVERED
    shipment.arrival()
    shipment.save()

    response = client_alice.post(url, data=action)
    AssertionHelper.HTTP_200(response,
                             entity_refs=AssertionHelper.EntityRef(
                                 resource='Shipment',
                                 pk=shipment.id,
                                 attributes={'state': TransitState.DELIVERED.name})
                             )

    updated_parameters = response.json()['data']['attributes']
    assert datetimeAlmostEqual(dt_parse(updated_parameters['delivery_act']))

    # Can't pickup/arrive/deliver when DELIVERED
    response = client_alice.post(url, data=action)
    AssertionHelper.HTTP_400(response,
                             error='Action DROP_OFF not available while Shipment is in state DELIVERED',
                             pointer='action_type')

    action = {
        'action_type': ActionType.PICK_UP.name
    }
    response = client_alice.post(url, data=action)
    AssertionHelper.HTTP_400(response,
                             error='Action PICK_UP not available while Shipment is in state DELIVERED',
                             pointer='action_type')

    action = {
        'action_type': ActionType.ARRIVAL.name
    }
    response = client_alice.post(url, data=action)
    AssertionHelper.HTTP_400(response,
                             error='Action ARRIVAL not available while Shipment is in state DELIVERED',
                             pointer='action_type')

    action = {
        'action_type': ActionType.DROP_OFF.name
    }
    response = client_alice.post(url, data=action)
    AssertionHelper.HTTP_400(response,
                             error='Action DROP_OFF not available while Shipment is in state DELIVERED',
                             pointer='action_type')


@pytest.mark.django_db
def test_dropoff_asset_physical_id(client_alice, shipment):
    assert shipment.delivery_act is None

    # Set NFC/Asset ID
    super_secret_nfc_id = 'package123'

    shipment.pick_up(asset_physical_id=super_secret_nfc_id)
    shipment.save()

    shipment.arrival()
    shipment.save()

    url = reverse('shipment-actions', kwargs={'version': 'v1', 'shipment_pk': shipment.id})
    action = {
        'action_type': ActionType.DROP_OFF.name
    }

    # asset_physical_id set on instance but no raw_asset_physical_id should return error
    response = client_alice.post(url, data=action)
    AssertionHelper.HTTP_403(response, error='Hash of asset tag does not match value specified in '
                                             'Shipment.asset_physical_id')

    action['raw_asset_physical_id'] = 'package987'

    # asset_physical_id set on instance but incorrect raw_asset_physical_id should return error
    response = client_alice.post(url, data=action)
    AssertionHelper.HTTP_403(response, error='Hash of asset tag does not match value specified in '
                                             'Shipment.asset_physical_id')

    action['raw_asset_physical_id'] = super_secret_nfc_id

    # asset_physical_id set on instance and matching raw_asset_physical_id should succeed
    response = client_alice.post(url, data=action)
    AssertionHelper.HTTP_200(response,
                             entity_refs=AssertionHelper.EntityRef(
                                 resource='Shipment',
                                 pk=shipment.id,
                                 attributes={'state': TransitState.DELIVERED.name})
                             )


@pytest.mark.django_db
def test_readonly_state(shipment):
    assert TransitState(shipment.state) == TransitState.AWAITING_PICKUP

    with pytest.raises(AttributeError):
        shipment.state = TransitState.IN_TRANSIT
    shipment.save()

    assert TransitState(shipment.state) == TransitState.AWAITING_PICKUP


@pytest.mark.django_db
def test_shadow_state_updates(mocked_iot_api, shipment_with_device):
    call_count = mocked_iot_api.call_count
    shipment_with_device.pick_up()
    shipment_with_device.save()
    call_count += 1  # Status should have been updated in the shadow
    assert call_count == mocked_iot_api.call_count
