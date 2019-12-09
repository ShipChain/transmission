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
from shipchain_common.test_utils import create_form_content

from apps.notes.models import ShipmentNote


# 207 characters note message
MESSAGE_1 = 'Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do eiusmod tempor incididunt ut labore et ' \
            'dolore magna aliqua. Nisl purus in mollis nunc sed id semper risus. Nulla facilisi etiam dignissim diam.'

# More than 500 characters
MESSAGE_2 = MESSAGE_1 + 'Eu mi bibendum neque egestas. Dui faucibus in ornare quam viverra. Adipiscing elit' \
                                 ' duis tristique sollicitudin. Faucibus pulvinar elementum integer enim. Sed risus ' \
                                 'pretium quam vulputate dignissim suspendisse in est ante. Sit amet cursus sit amet ' \
                                 'dictum sit amet justo. Laoreet sit amet cursus sit amet dictum sit amet justo. ' \
                                 'Scelerisque in dictum non consectetur a erat nam at lectus. Porttitor rhoncus ' \
                                 'dolor purus non enim.'

# Contains special word "ShipChain"
MESSAGE_3 = MESSAGE_1 + 'ShipChain'

# Shipper note message
MESSAGE_4 = 'Shipper note about the shipment.'


@pytest.fixture
def shipment_notes(user, shipper_user, shipment):
    return [
        ShipmentNote.objects.create(author_id=user.id, message=MESSAGE_1, shipment=shipment),
        ShipmentNote.objects.create(author_id=user.id, message=MESSAGE_3, shipment=shipment),
        ShipmentNote.objects.create(author_id=shipper_user.id, message=MESSAGE_4, shipment=shipment),
    ]


@pytest.mark.django_db
def test_create_shipment_note(user, api_client, shipper_api_client, unauthenticated_api_client,
                              shipment, mocked_is_shipper):
    url = reverse('shipment-notes-list', kwargs={'version': 'v1', 'shipment_pk': shipment.id})
    create_note_data, content_type = create_form_content({'message': MESSAGE_1})

    # An unauthenticated user cannot create a shipment note
    response = unauthenticated_api_client.post(url, {'message': MESSAGE_1}, format='json')
    assert response.status_code == status.HTTP_403_FORBIDDEN

    # An authenticated request with a empty message should fail
    response = api_client.post(url, {'message': ''}, format='json')
    assert response.status_code == status.HTTP_400_BAD_REQUEST

    # An authenticated request with a message with more than 500 characters should fail
    response = api_client.post(url, {'message': MESSAGE_2}, format='json')
    assert response.status_code == status.HTTP_400_BAD_REQUEST

    # An authenticated user can create a shipment note
    response = api_client.post(url, create_note_data, content_type=content_type)
    assert response.status_code == status.HTTP_201_CREATED
    note_data = response.json()['data']
    assert len(note_data['attributes']['message']) == len(MESSAGE_1)
    assert note_data['attributes']['author_id'] == user.id

    # A shipper also valid for moderator and carrier can add a shipment note
    response = shipper_api_client.post(url, {'message': MESSAGE_1}, format='json')
    assert response.status_code == status.HTTP_201_CREATED
    note_data = response.json()['data']
    assert len(note_data['attributes']['message']) == len(MESSAGE_1)
    assert note_data['attributes']['author_id'] == mocked_is_shipper.id     # author_id is the shipper Id


@pytest.mark.django_db
def test_update_delete_shipment_note(api_client, shipment, shipment_notes):
    url = reverse('shipment-notes-detail', kwargs={'version': 'v1', 'shipment_pk': shipment.id,
                                                   'pk': shipment_notes[0].id})

    update_note_data = {'message': 'Update message!'}

    # A note object cannot be updated
    response = api_client.patch(url, update_note_data, format='json')
    assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED

    # Similarly, a note object cannot be deleted
    response = api_client.delete(url)
    assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED


@pytest.mark.django_db
def test_list_search_filter(user, api_client, shipper_api_client, unauthenticated_api_client, shipment,
                            mocked_is_shipper, shipment_notes):
    url = reverse('shipment-notes-list', kwargs={'version': 'v1', 'shipment_pk': shipment.id})

    # An unauthenticated user cannot list a shipment notes
    response = unauthenticated_api_client.get(url)
    assert response.status_code == status.HTTP_403_FORBIDDEN

    # A shipment owner can list all notes associated
    response = api_client.get(url)
    assert response.status_code == status.HTTP_200_OK
    notes_data = response.json()['data']
    assert len(notes_data) == len(shipment_notes)

    # A shipment shipper can list all notes associated
    response = shipper_api_client.get(url)
    assert response.status_code == status.HTTP_200_OK
    notes_data = response.json()['data']
    assert len(notes_data) == len(shipment_notes)

    # There is only one note authored by the shipper
    response = api_client.get(f'{url}?author_id={mocked_is_shipper.id}')
    notes_data = response.json()['data']
    assert len(notes_data) == 1
    assert notes_data[0]['attributes']['author_id'] == mocked_is_shipper.id

    # There is only one note containing the word "ShipChain"
    response = api_client.get(f'{url}?search=shipchain')
    notes_data = response.json()['data']
    assert len(notes_data) == 1
    assert 'ShipChain' in notes_data[0]['attributes']['message']
