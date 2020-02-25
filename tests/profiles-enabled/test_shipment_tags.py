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

from apps.shipments.models import ShipmentTag


@pytest.fixture
def shipment_tag_creation_data():
    return {
        'tag_type': '*Export-Shipment*',
        'tag_value': '-->Europe'
    }

@pytest.fixture
def shipment_tag_location():
    return {
        'tag_type': 'Destination',
        'tag_value': 'Toronto'
    }

@pytest.fixture
def missing_tag_type_creation_data():
    return {
        'tag_value': '-->Europe'
    }

@pytest.fixture
def missing_tag_value_creation_data():
    return {
        'tag_type': '*Export-Shipment*',
    }

@pytest.fixture
def space_in_tag_type_creation_data():
    return {
        'tag_type': '*Export Shipment*',
        'tag_value': '-->Europe'
    }

@pytest.fixture
def space_in_tag_value_creation_data():
    return {
        'tag_type': '*Export-Shipment*',
        'tag_value': 'United Kingdom'
    }

@pytest.fixture
def entity_shipment_relationship(json_asserter, shipment):
    return json_asserter.EntityRef(resource='Shipment', pk=shipment.id)


@pytest.fixture
def shipment_tags(user, shipment, second_shipment, shipment_tag_creation_data, shipment_tag_location):
    tags = []
    tags.append(ShipmentTag.objects.create(tag_type=shipment_tag_creation_data['tag_type'],
                                           tag_value=shipment_tag_creation_data['tag_value'],
                                           shipment_id=shipment.id,
                                           user_id=uuid.UUID(user.id)))

    tags.append(ShipmentTag.objects.create(tag_type=shipment_tag_location['tag_type'],
                                           tag_value=shipment_tag_location['tag_value'],
                                           shipment_id=second_shipment.id,
                                           user_id=uuid.UUID(user.id)))

    return tags

@pytest.fixture
def entity_shipment_tagged(json_asserter, shipment, shipment_tags):
    return json_asserter.EntityRef(resource='Shipment',
                                   pk=shipment.id,
                                   relationships={
                                       'shipment_tags': json_asserter.EntityRef(
                                           resource='ShipmentTag', pk=shipment_tags[0].id)}
                                   )

@pytest.fixture
def entity_second_shipment_tagged(json_asserter, second_shipment, shipment_tags):
    return json_asserter.EntityRef(resource='Shipment',
                                   pk=second_shipment.id,
                                   relationships={
                                       'shipment_tags': json_asserter.EntityRef(
                                           resource='ShipmentTag', pk=shipment_tags[1].id)}
                                   )

@pytest.fixture
def entity_shipment_tag_included(json_asserter, shipment, shipment_tags, shipment_tag_creation_data):
    return json_asserter.EntityRef(resource='ShipmentTag',
                                   pk=str(shipment_tags[0].id),
                                   attributes={
                                       'tag_type': shipment_tag_creation_data['tag_type'],
                                        'tag_value': shipment_tag_creation_data['tag_value']}
                                   )

@pytest.fixture
def entity_second_shipment_tag_included(json_asserter, second_shipment, shipment_tags, shipment_tag_location):
    return json_asserter.EntityRef(resource='ShipmentTag',
                                   pk=str(shipment_tags[1].id),
                                   attributes={
                                       'tag_type': shipment_tag_location['tag_type'],
                                        'tag_value': shipment_tag_location['tag_value']}
                                   )


@pytest.mark.django_db
def test_org_user_shipment_tag(user, api_client, unauthenticated_api_client, shipment, shipment_tag_creation_data,
                               missing_tag_type_creation_data, missing_tag_value_creation_data,
                               space_in_tag_type_creation_data, space_in_tag_value_creation_data,
                               entity_shipment_relationship, json_asserter):

    url = reverse('shipment-tags-list', kwargs={'version': 'v1', 'shipment_pk': shipment.id})

    # An unauthenticated user cannot tag a shipment
    response = unauthenticated_api_client.post(url, shipment_tag_creation_data, format='json')
    json_asserter.HTTP_403(response, error='You do not have permission to perform this action.')

    # An org user cannot tag a shipment with missing tag_type in creation data
    response = api_client.post(url, missing_tag_type_creation_data, format='json')
    json_asserter.HTTP_400(response, error='This field is required.')

    # An org user cannot tag a shipment with missing tag_value in creation data
    response = api_client.post(url, missing_tag_value_creation_data, format='json')
    json_asserter.HTTP_400(response, error='This field is required.')

    # An org user cannot tag a shipment with space in tag_value field creation data
    response = api_client.post(url, space_in_tag_value_creation_data, format='json')
    json_asserter.HTTP_400(response, error='Space(s) not allowed in this field')

    # An org user cannot tag a shipment with space in tag_type field creation data
    response = api_client.post(url, space_in_tag_type_creation_data, format='json')
    json_asserter.HTTP_400(response, error='Space(s) not allowed in this field')

    # An org user with proper tag data definition, should tag a shipment
    response = api_client.post(url, shipment_tag_creation_data, format='json')
    json_asserter.HTTP_201(response,
                           entity_refs=json_asserter.EntityRef(
                               resource='ShipmentTag',
                               attributes={'tag_type': shipment_tag_creation_data['tag_type'],
                                           'tag_value': shipment_tag_creation_data['tag_value'],
                                           'user_id': user.id},
                               relationships={'shipment': entity_shipment_relationship})
                           )

    # Trying to tag a shipment with an existing (tag_type, tag_value) pair should fail
    response = api_client.post(url, shipment_tag_creation_data, format='json')
    json_asserter.HTTP_400(response, error=f'This shipment already has a tag with, '
                                           f'`tag_type: {shipment_tag_creation_data["tag_type"]}` and '
                                           f'`tag_value: {shipment_tag_creation_data["tag_value"]}`.')

@pytest.mark.django_db
def test_shipper_carrier_moderator_shipment_tag(user_2, user2_api_client, mocked_is_shipper, mocked_not_carrier,
                                                mocked_not_moderator, shipment, shipment_tag_creation_data,
                                                entity_shipment_relationship, json_asserter):

    url = reverse('shipment-tags-list', kwargs={'version': 'v1', 'shipment_pk': shipment.id})

    # User_2 does not belong to the shipment organization but is the shipment shipper.
    # he should be able to tag the shipment
    response = user2_api_client.post(url, shipment_tag_creation_data, format='json')
    json_asserter.HTTP_201(response,
                           entity_refs=json_asserter.EntityRef(
                               resource='ShipmentTag',
                               attributes={'tag_type': shipment_tag_creation_data['tag_type'],
                                           'tag_value': shipment_tag_creation_data['tag_value'],
                                           'user_id': user_2.id},
                               relationships={'shipment': entity_shipment_relationship})
                           )

@pytest.mark.django_db
def test_authenticated_user_not_in_shipment_org(user2_api_client, mocked_not_shipper, mocked_not_carrier,
                                                mocked_not_moderator, shipment, shipment_tag_creation_data,
                                                json_asserter):

    url = reverse('shipment-tags-list', kwargs={'version': 'v1', 'shipment_pk': shipment.id})

    # User_2 does not belong to the shipment organization and is neither shipper, carrier nor moderator.
    # he should not be able to tag the shipment
    response = user2_api_client.post(url, shipment_tag_creation_data, format='json')
    json_asserter.HTTP_403(response, error='You do not have permission to perform this action.')

@pytest.mark.django_db
def test_list_tagged_shipments(api_client, shipment_tag_creation_data, shipment_tag_location, shipment_tags,
                               entity_shipment_tagged, entity_second_shipment_tagged, entity_shipment_tag_included,
                               entity_second_shipment_tag_included, json_asserter):

    shipment_list_url = reverse('shipment-list', kwargs={'version': 'v1'})

    response = api_client.get(shipment_list_url)
    json_asserter.HTTP_200(response,
                           is_list=True,
                           entity_refs=[entity_shipment_tagged, entity_second_shipment_tagged],
                           included=[entity_shipment_tag_included, entity_second_shipment_tag_included])

    # Test case insensitive shipment filter by tag_type, should return one entity.
    response = api_client.get(f'{shipment_list_url}?tag_type={shipment_tag_creation_data["tag_type"].upper()}')
    json_asserter.HTTP_200(response,
                           is_list=True,
                           entity_refs=entity_shipment_tagged,
                           included=entity_shipment_tag_included)

    # Test case insensitive shipment filter by tag_value, should return one entity.
    response = api_client.get(f'{shipment_list_url}?tag_value={shipment_tag_location["tag_value"].upper()}')
    json_asserter.HTTP_200(response,
                           is_list=True,
                           entity_refs=entity_second_shipment_tagged,
                           included=entity_second_shipment_tag_included)

    # Test search shipment through tag fields, should return one entity.
    response = api_client.get(f'{shipment_list_url}?search={shipment_tag_location["tag_value"][:4].lower()}')
    json_asserter.HTTP_200(response,
                           is_list=True,
                           entity_refs=entity_second_shipment_tagged,
                           included=entity_second_shipment_tag_included)
