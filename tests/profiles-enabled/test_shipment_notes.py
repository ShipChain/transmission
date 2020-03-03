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

from apps.shipments.models import ShipmentNote


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
def username(user):
    return f'{user.username.split("@")[0]} [{user.token.payload["organization_name"]}]'

@pytest.fixture
def username2(user2):
    return f'{user2.username.split("@")[0]} [{user2.token.payload["organization_name"]}]'

@pytest.fixture
def shipper_username(shipper_user):
    # The shipper does not belong to any organization
    return shipper_user.username.split("@")[0]

@pytest.fixture
def shipment_notes(user, user2, username, shipper_user, shipper_username, username2, shipment, org2_shipment):
    return [
        ShipmentNote.objects.create(user_id=user.id, username=username, message=MESSAGE_1, shipment=shipment),
        ShipmentNote.objects.create(user_id=user.id, username=username, message=MESSAGE_3, shipment=shipment),
        ShipmentNote.objects.create(user_id=shipper_user.id, username=shipper_username, message=MESSAGE_4, shipment=shipment),
        ShipmentNote.objects.create(user_id=user2.id, username=username2, message=MESSAGE_4, shipment=org2_shipment),
    ]


@pytest.mark.django_db
def test_create_shipment_note(user, username, api_client, shipper_api_client, shipper_username,
                              unauthenticated_api_client, shipment, mocked_is_shipper, entity_ref_shipment,
                              json_asserter):

    url = reverse('shipment-notes-list', kwargs={'version': 'v1', 'shipment_pk': shipment.id})
    create_note_data, content_type = create_form_content({'message': MESSAGE_1})

    # An unauthenticated user cannot create a shipment note
    response = unauthenticated_api_client.post(url, {'message': MESSAGE_1}, format='json')
    json_asserter.HTTP_403(response, error='You do not have permission to perform this action.')

    # An authenticated request with a empty message should fail
    response = api_client.post(url, {'message': ''}, format='json')
    json_asserter.HTTP_400(response, error='This field may not be blank.', pointer='message')

    # An authenticated request with a message with more than 500 characters should fail
    response = api_client.post(url, {'message': MESSAGE_2}, format='json')
    json_asserter.HTTP_400(response,
                           error='Ensure this value has at most 500 characters (it has 632).',
                           pointer='message')

    # An authenticated user can create a shipment note
    response = api_client.post(url, create_note_data, content_type=content_type)

    json_asserter.HTTP_201(response,
                           entity_refs=json_asserter.EntityRef(resource='ShipmentNote',
                                                               attributes={
                                                                   'message': MESSAGE_1,
                                                                   'user_id': user.id,
                                                                   'username': username},
                                                               relationships={'shipment': entity_ref_shipment})
                           )

    # A shipper also valid for moderator and carrier can add a shipment note
    response = shipper_api_client.post(url, {'message': MESSAGE_1}, format='json')

    json_asserter.HTTP_201(response,
                           entity_refs=json_asserter.EntityRef(resource='ShipmentNote',
                                                               attributes={
                                                                   'message': MESSAGE_1,
                                                                   'user_id': mocked_is_shipper.id,
                                                                   'username': shipper_username},
                                                               relationships={'shipment': entity_ref_shipment})
                           )


@pytest.mark.django_db
def test_non_org_user_shipment_note_creation(user2_api_client, shipment, mocked_not_shipper, mocked_not_carrier,
                                             mocked_not_moderator, json_asserter):
    url = reverse('shipment-notes-list', kwargs={'version': 'v1', 'shipment_pk': shipment.id})

    # user2 is an authenticated user from another Org. he cannot create a shipment note
    response = user2_api_client.post(url, {'message': MESSAGE_1}, format='json')
    json_asserter.HTTP_403(response, error='You do not have permission to perform this action.')


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
def test_list_search_filter(api_client, shipper_api_client, unauthenticated_api_client, shipment,
                            mocked_is_shipper, shipment_notes, entity_ref_shipment, json_asserter):

    url = reverse('shipment-notes-list', kwargs={'version': 'v1', 'shipment_pk': shipment.id})

    # An unauthenticated user cannot list a shipment notes
    response = unauthenticated_api_client.get(url)
    assert response.status_code == status.HTTP_403_FORBIDDEN
    json_asserter.HTTP_403(response, error='You do not have permission to perform this action.')

    # A shipment owner can list all notes associated
    response = api_client.get(url)
    json_asserter.HTTP_200(response, is_list=True)
    notes_data = response.json()['data']
    assert len(notes_data) == len(shipment_notes) - 1

    # A shipper can list only the notes associated to the relative shipment
    response = shipper_api_client.get(url)
    json_asserter.HTTP_200(response, is_list=True)
    notes_data = response.json()['data']
    assert len(notes_data) == len(shipment_notes) - 1

    # There is only one note authored by the shipper
    response = api_client.get(f'{url}?user_id={mocked_is_shipper.id}')
    notes_data = response.json()['data']
    assert len(notes_data) == 1
    json_asserter.HTTP_200(response,
                           is_list=True,
                           entity_refs=[json_asserter.EntityRef(resource='ShipmentNote',
                                                               attributes={
                                                                   'message': shipment_notes[2].message,
                                                                   'user_id': shipment_notes[2].user_id,
                                                                   'username': shipment_notes[2].username},
                                                               relationships={'shipment': entity_ref_shipment})]
                           )

    # There is only one note containing the word "ShipChain"
    response = api_client.get(f'{url}?search=shipchain')
    notes_data = response.json()['data']
    assert len(notes_data) == 1
    json_asserter.HTTP_200(response,
                           is_list=True,
                           entity_refs=[json_asserter.EntityRef(resource='ShipmentNote',
                                                                attributes={
                                                                    'message': shipment_notes[1].message,
                                                                    'user_id': shipment_notes[1].user_id,
                                                                    'username': shipment_notes[1].username},
                                                                relationships={'shipment': entity_ref_shipment})]
                           )
