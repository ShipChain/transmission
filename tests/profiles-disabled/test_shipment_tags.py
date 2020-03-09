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
from rest_framework.reverse import reverse
from shipchain_common.utils import random_id


USER_ID = random_id()


@pytest.fixture
def shipment_tag_creation_data():
    return {
        'tag_type': '*Export-Shipment*',
        'tag_value': '-->Europe',
        'user_id': USER_ID,
    }

@pytest.fixture
def shipment_tag_creation_missing_user_id():
    return {
        'tag_type': 'Destination',
        'tag_value': 'Toronto'
    }

@pytest.fixture
def entity_shipment_relationship(json_asserter, shipment):
    return json_asserter.EntityRef(resource='Shipment', pk=shipment.id)


@pytest.mark.django_db
def test_profiles_disabled_shipment_tag_creation(unauthenticated_api_client, shipment, shipment_tag_creation_data,
                                                 shipment_tag_creation_missing_user_id, entity_shipment_relationship,
                                                 json_asserter):

    url = reverse('shipment-tags-list', kwargs={'version': 'v1', 'shipment_pk': shipment.id})

    # A request without user_id should fail
    response = unauthenticated_api_client.post(url, shipment_tag_creation_missing_user_id, format='json')
    json_asserter.HTTP_400(response, error='This field is required.')

    response = unauthenticated_api_client.post(url, shipment_tag_creation_data, format='json')
    json_asserter.HTTP_201(response,
                           entity_refs=json_asserter.EntityRef(
                               resource='ShipmentTag',
                               attributes={'tag_type': shipment_tag_creation_data['tag_type'],
                                           'tag_value': shipment_tag_creation_data['tag_value'],
                                           'user_id': USER_ID},
                               relationships={'shipment': entity_shipment_relationship})
                           )
