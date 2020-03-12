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

import uuid

import pytest
from rest_framework.reverse import reverse
from shipchain_common.test_utils import AssertionHelper
from shipchain_common.utils import random_id

VALID_UUID4 = random_id()


@pytest.mark.django_db
def test_shipment_creation_with_assignee(client_alice, mocked_is_shipper, mocked_storage_credential, shipment):

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
    response = client_alice.post(url, data=invalid_uuid4_data)
    AssertionHelper.HTTP_400(response, error='Must be a valid UUID.', pointer='assignee_id')

    # With a valid assignee ID the request should succeed
    response = client_alice.post(url, data=valid_uuid4_data)
    AssertionHelper.HTTP_202(response,
                             entity_refs=AssertionHelper.EntityRef(
                                 resource='Shipment', attributes={'assignee_id': VALID_UUID4})
                             )


@pytest.mark.django_db
def test_shipment_update_with_assignee(client_alice, shipment):

    url = reverse('shipment-detail', kwargs={'version': 'v1', 'pk': shipment.id})

    valid_uuid4_data = {
        'assignee_id': VALID_UUID4,
    }

    invalid_uuid4_data = {
        'assignee_id': VALID_UUID4 + '12',
    }

    # A shipment cannot be updated with an invalid assignee ID
    response = client_alice.patch(url, data=invalid_uuid4_data)
    AssertionHelper.HTTP_400(response, error='Must be a valid UUID.', pointer='assignee_id')

    # With a valid assignee ID the request should succeed
    response = client_alice.patch(url, data=valid_uuid4_data)
    AssertionHelper.HTTP_202(response,
                             entity_refs=AssertionHelper.EntityRef(
                                 resource='Shipment', pk=shipment.id, attributes={'assignee_id': VALID_UUID4})
                             )


@pytest.mark.django_db
def test_shipment_assignee_filter(client_alice, shipment, second_shipment):

    url = reverse('shipment-detail', kwargs={'version': 'v1', 'pk': shipment.id})

    shipment.assignee_id = uuid.UUID(VALID_UUID4)
    shipment.save()

    invalid_uuid = VALID_UUID4 + '12'

    # A  filter with an invalid UUID value should fail
    response = client_alice.get(f'{url}?assignee_id={invalid_uuid}')
    AssertionHelper.HTTP_400(response, error='Enter a valid UUID.')

    # There is only one shipment with the provided assignee ID
    response = client_alice.get(f'{url}?assignee_id={VALID_UUID4}')
    AssertionHelper.HTTP_200(response,
                             is_list=False,
                             entity_refs=AssertionHelper.EntityRef(
                                 resource='Shipment', attributes={'assignee_id': VALID_UUID4})
                             )
