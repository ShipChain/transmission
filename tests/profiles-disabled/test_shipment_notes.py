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


import pytest

from rest_framework import status
from rest_framework.reverse import reverse
from shipchain_common.utils import random_id
from shipchain_common.test_utils import create_form_content


USER_ID = random_id()

# 207 characters note message
MESSAGE = 'Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do eiusmod tempor incididunt ut labore et ' \
            'dolore magna aliqua. Nisl purus in mollis nunc sed id semper risus. Nulla facilisi etiam dignissim diam.'


@pytest.mark.django_db
def test_create_shipment_note(unauthenticated_api_client, shipment):
    url = reverse('shipment-notes-list', kwargs={'version': 'v1', 'shipment_pk': shipment.id})
    bad_shipment_url = reverse('shipment-notes-list', kwargs={'version': 'v1', 'shipment_pk': random_id()})

    create_note_data, content_type = create_form_content({
        'message': MESSAGE,
        'author_id': USER_ID})

    # An unauthenticated user cannot create a shipment note without specifying the author
    response = unauthenticated_api_client.post(url, {'message': MESSAGE}, format='json')
    assert response.status_code == status.HTTP_400_BAD_REQUEST

    # A shipment note cannot be created for a non existing shipment
    response = unauthenticated_api_client.post(bad_shipment_url, create_note_data, content_type=content_type)
    assert response.status_code == status.HTTP_400_BAD_REQUEST

    # An authenticated user with a specified author can create a shipment note
    response = unauthenticated_api_client.post(url, create_note_data, content_type=content_type)
    assert response.status_code == status.HTTP_201_CREATED
    note_data = response.json()['data']
    assert len(note_data['attributes']['message']) == len(MESSAGE)
    assert note_data['attributes']['author_id'] == USER_ID
