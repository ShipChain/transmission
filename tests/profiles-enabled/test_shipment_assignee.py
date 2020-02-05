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

import pytest

from rest_framework import status
from rest_framework.reverse import reverse
from shipchain_common.utils import random_id


VALID_UUID4 = random_id()


@pytest.mark.django_db
def test_shipment_creation_with_assignee(api_client, mocked_engine_rpc, mocked_is_shipper, mocked_storage_credential,
                                         shipment, json_asserter):

    url = reverse('shipment-list', kwargs={'version': 'v1'})

    valid_uuid4_data = {
        'storage_credentials_id': shipment.storage_credentials_id,
        'shipper_wallet_id': shipment.shipper_wallet_id,
        'carrier_wallet_id': shipment.carrier_wallet_id,
        'assignee_id': VALID_UUID4,
    }

    invalid_uuid4_data = {
        'storage_credentials_id': shipment.storage_credentials_id,
        'shipper_wallet_id': shipment.shipper_wallet_id,
        'carrier_wallet_id': shipment.carrier_wallet_id,
        'assignee_id': VALID_UUID4[:-1],
    }

    # A shipment cannot be created with an invalid assignee ID
    response = api_client.post(url, data=invalid_uuid4_data, format='json')
    json_asserter.HTTP_400(response, error='Must be a valid UUID.')

    # With a valid assignee ID the request should succeed
    response = api_client.post(url, data=valid_uuid4_data, format='json')
    response_data = response.json()['data']
    assert response.status_code == status.HTTP_202_ACCEPTED
    assert response_data['attributes']['assignee_id'] == VALID_UUID4



@pytest.mark.django_db
def test_shipment_update_with_assignee(api_client, mocked_engine_rpc, shipment, json_asserter):

    url = reverse('shipment-detail', kwargs={'version': 'v1', 'pk': shipment.id})

    valid_uuid4_data = {
        'assignee_id': VALID_UUID4,
    }

    invalid_uuid4_data = {
        'assignee_id': VALID_UUID4 + '12',
    }

    # A shipment cannot be updated with an invalid assignee ID
    response = api_client.patch(url, data=invalid_uuid4_data, format='json')
    json_asserter.HTTP_400(response, error='Must be a valid UUID.')

    # With a valid assignee ID the request should succeed
    response = api_client.patch(url, data=valid_uuid4_data, format='json')
    response_data = response.json()['data']
    assert response.status_code == status.HTTP_202_ACCEPTED
    assert response_data['attributes']['assignee_id'] == VALID_UUID4
