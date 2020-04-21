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
def shipment_tags(org_id_alice, shipment, second_shipment, shipment_tag_creation_data, shipment_tag_location):
    return [
        ShipmentTag.objects.create(
            tag_type=shipment_tag_creation_data['tag_type'],
            tag_value=shipment_tag_creation_data['tag_value'],
            shipment_id=shipment.id,
            owner_id=uuid.UUID(org_id_alice)
        ),

        ShipmentTag.objects.create(
            tag_type=shipment_tag_location['tag_type'],
            tag_value=shipment_tag_location['tag_value'],
            shipment_id=second_shipment.id,
            owner_id=uuid.UUID(org_id_alice)
        ),
    ]


class TestShipmentTagOnCreate:
    url = reverse('shipment-list', kwargs={'version': 'v1'})

    @pytest.fixture(autouse=True)
    def set_up(self, successful_shipment_create_profiles_assertions, mock_successful_wallet_owner_calls, profiles_ids,
               mocked_engine_rpc, mocked_iot_api):
        self.assertions = successful_shipment_create_profiles_assertions
        self.wallet_mocking = mock_successful_wallet_owner_calls
        self.base_call = profiles_ids

    def test_create_requires_uniqueness(self, client_alice):
        self.base_call['tags'] = [
            {
                'tag_value': 'tag_value',
                'tag_type': 'tag_type'
            },
            {
                'tag_value': 'tag_value',
                'tag_type': 'tag_type'
            }
        ]
        response = client_alice.post(self.url, self.base_call)
        AssertionHelper.HTTP_400(response, 'Tags field cannot contain duplicates')

        self.wallet_mocking.assert_calls(self.assertions)

    def test_create_requires_fields(self, client_alice):
        self.base_call['tags'] = [
            {
                'tag_type': 'tag_type'
            },
        ]
        response = client_alice.post(self.url, self.base_call)
        AssertionHelper.HTTP_400(response, 'Tags items must contain `tag_value` and `tag_type`.')

        self.wallet_mocking.assert_calls(self.assertions)

        self.base_call['tags'] = [
            {
                'tag_value': 'tag_value'
            },
        ]
        response = client_alice.post(self.url, self.base_call)
        AssertionHelper.HTTP_400(response, 'Tags items must contain `tag_value` and `tag_type`.')

        self.wallet_mocking.assert_calls(self.assertions)

    def test_can_create(self, client_alice):
        self.base_call['tags'] = [
            {
                'tag_value': 'tag_value',
                'tag_type': 'tag_type'
            }, {
                'tag_value': 'tag_value_two',
                'tag_type': 'tag_type'
            },
        ]
        response = client_alice.post(self.url, self.base_call)
        AssertionHelper.HTTP_202(response, included=[
            AssertionHelper.EntityRef(resource='ShipmentTag',
                                      attributes={
                                          'tag_type': 'tag_type',
                                          'tag_value': 'tag_value'
                                      }),
            AssertionHelper.EntityRef(resource='ShipmentTag',
                                      attributes={
                                          'tag_type': 'tag_type',
                                          'tag_value': 'tag_value_two'
                                      })
        ])

        self.wallet_mocking.assert_calls(self.assertions)


class TestShipmentTagUpdate:
    @pytest.fixture(autouse=True)
    def set_up(self, shipment_tags, nonsuccessful_wallet_owner_calls_assertions):
        self.shipment_tags = shipment_tags
        self.nonsuccessful_wallet_owner_calls_assertions = nonsuccessful_wallet_owner_calls_assertions
        for tag in shipment_tags:
            setattr(self, f'url_{tag.tag_type}', reverse(
                'shipment-tags-detail',
                kwargs={'version': 'v1', 'shipment_pk': tag.shipment.id, 'pk': tag.id}
            ))

    def test_update_requires_authentication(self, api_client, mock_non_wallet_owner_calls):
        response = api_client.patch(getattr(self, f'url_{self.shipment_tags[0].tag_type}'), {
            'tag_value': 'new tag value'
        })
        AssertionHelper.HTTP_403(response, error='You do not have permission to perform this action.')

    def test_owner_can_update(self, client_alice, org_id_alice):
        response = client_alice.patch(getattr(self, f'url_{self.shipment_tags[0].tag_type}'), {
            'tag_value': 'new_tag_value'
        })
        AssertionHelper.HTTP_200(response,
                                 entity_refs=AssertionHelper.EntityRef(
                                     resource='ShipmentTag',
                                     attributes={'tag_type': self.shipment_tags[0].tag_type,
                                                 'tag_value': 'new_tag_value',
                                                 'owner_id': org_id_alice},
                                     relationships={
                                         'shipment': AssertionHelper.EntityRef(resource='Shipment',
                                                                               pk=self.shipment_tags[0].shipment.id)
                                     })
                                 )

    def test_cannot_update_tag_type(self, client_alice, org_id_alice):
        response = client_alice.patch(getattr(self, f'url_{self.shipment_tags[0].tag_type}'), {
            'tag_type': 'new_tag_type'
        })
        AssertionHelper.HTTP_200(response,
                                 entity_refs=AssertionHelper.EntityRef(
                                     resource='ShipmentTag',
                                     attributes={'tag_type': self.shipment_tags[0].tag_type,
                                                 'tag_value': self.shipment_tags[0].tag_value,
                                                 'owner_id': org_id_alice},
                                     relationships={
                                         'shipment': AssertionHelper.EntityRef(resource='Shipment',
                                                                               pk=self.shipment_tags[0].shipment.id)
                                     })
                                 )

    def test_tag_value_uniqueness(self, client_alice, org_id_alice, shipment):
        ShipmentTag.objects.create(
            tag_type=self.shipment_tags[0].tag_type,
            tag_value=self.shipment_tags[1].tag_value,
            shipment_id=shipment.id,
            owner_id=uuid.UUID(org_id_alice)
        ),
        response = client_alice.patch(getattr(self, f'url_{self.shipment_tags[0].tag_type}'), {
            'tag_value': self.shipment_tags[1].tag_value
        })
        AssertionHelper.HTTP_400(response,
                                 'This shipment already has a tag with the provided [tag_type] and [tag_value].')


class TestShipmentTagDeletion:
    @pytest.fixture(autouse=True)
    def set_up(self, shipment_tags, nonsuccessful_wallet_owner_calls_assertions):
        self.shipment_tags = shipment_tags
        self.nonsuccessful_wallet_owner_calls_assertions = nonsuccessful_wallet_owner_calls_assertions
        for tag in shipment_tags:
            setattr(self, f'url_{tag.tag_type}', reverse(
                'shipment-tags-detail',
                kwargs={'version': 'v1', 'shipment_pk': tag.shipment.id, 'pk': tag.id}
            ))

    def test_deletion_requires_authentication(self, api_client, mock_non_wallet_owner_calls):
        response = api_client.delete(getattr(self, f'url_{self.shipment_tags[0].tag_type}'))
        AssertionHelper.HTTP_403(response, error='You do not have permission to perform this action.')

    def test_owner_can_update(self, client_alice, org_id_alice):
        response = client_alice.delete(getattr(self, f'url_{self.shipment_tags[0].tag_type}'))
        AssertionHelper.HTTP_204(response)


@pytest.mark.django_db
def test_org_user_shipment_tag(org_id_alice, api_client, client_alice, shipment, shipment_tag_creation_data,
                               missing_tag_type_creation_data, missing_tag_value_creation_data,
                               space_in_tag_type_creation_data, space_in_tag_value_creation_data):

    url = reverse('shipment-tags-list', kwargs={'version': 'v1', 'shipment_pk': shipment.id})

    # An unauthenticated user cannot tag a shipment
    response = api_client.post(url, shipment_tag_creation_data)
    AssertionHelper.HTTP_403(response, error='You do not have permission to perform this action.')

    # An org user cannot tag a shipment with missing tag_type in creation data
    response = client_alice.post(url, missing_tag_type_creation_data)
    AssertionHelper.HTTP_400(response, error='This field is required.')

    # An org user cannot tag a shipment with missing tag_value in creation data
    response = client_alice.post(url, missing_tag_value_creation_data)
    AssertionHelper.HTTP_400(response, error='This field is required.')

    # An org user cannot tag a shipment with space in tag_value field creation data
    response = client_alice.post(url, space_in_tag_value_creation_data)
    AssertionHelper.HTTP_400(response, error='Space(s) not allowed in this field')

    # An org user cannot tag a shipment with space in tag_type field creation data
    response = client_alice.post(url, space_in_tag_type_creation_data)
    AssertionHelper.HTTP_400(response, error='Space(s) not allowed in this field')

    # An org user with proper tag data definition, should tag a shipment
    response = client_alice.post(url, shipment_tag_creation_data)
    AssertionHelper.HTTP_201(response,
                           entity_refs=AssertionHelper.EntityRef(
                               resource='ShipmentTag',
                               attributes={'tag_type': shipment_tag_creation_data['tag_type'],
                                           'tag_value': shipment_tag_creation_data['tag_value'],
                                           'owner_id': org_id_alice},
                               relationships={
                                   'shipment': AssertionHelper.EntityRef(resource='Shipment', pk=shipment.id)
                               })
                           )

    # Trying to tag a shipment with an existing (tag_type, tag_value) pair should fail
    response = client_alice.post(url, shipment_tag_creation_data)
    AssertionHelper.HTTP_400(response, error='This shipment already has a tag with the provided [tag_type] and [tag_value].')


@pytest.mark.django_db
def test_shipper_carrier_moderator_shipment_tag(org_id_bob, client_bob, mocked_is_shipper, mocked_not_carrier,
                                                mocked_not_moderator, shipment, shipment_tag_creation_data):

    url = reverse('shipment-tags-list', kwargs={'version': 'v1', 'shipment_pk': shipment.id})

    # User2 does not belong to the shipment organization but is the shipment shipper.
    # he should be not able to tag the shipment
    response = client_bob.post(url, shipment_tag_creation_data)
    AssertionHelper.HTTP_403(response, error='You do not have permission to perform this action.')


@pytest.mark.django_db
def test_authenticated_user_not_in_shipment_org(client_bob, mocked_not_shipper, mocked_not_carrier,
                                                mocked_not_moderator, shipment, shipment_tag_creation_data):

    url = reverse('shipment-tags-list', kwargs={'version': 'v1', 'shipment_pk': shipment.id})

    # User2 does not belong to the shipment organization and is neither shipper, carrier nor moderator.
    # he should not be able to tag the shipment
    response = client_bob.post(url, shipment_tag_creation_data)
    AssertionHelper.HTTP_403(response, error='You do not have permission to perform this action.')


@pytest.mark.django_db
def test_list_tagged_shipments(client_alice, shipment_tag_creation_data, shipment_tag_location,
                               shipment_tags, shipment, second_shipment):

    shipment_list_url = reverse('shipment-list', kwargs={'version': 'v1'})

    response = client_alice.get(shipment_list_url)
    AssertionHelper.HTTP_200(response,
                             is_list=True,
                             entity_refs=[
                                 AssertionHelper.EntityRef(resource='Shipment',
                                                           pk=shipment.id,
                                                           relationships={
                                                               'tags': AssertionHelper.EntityRef(
                                                                   resource='ShipmentTag', pk=shipment_tags[0].id)
                                                           }),
                                 AssertionHelper.EntityRef(resource='Shipment',
                                                           pk=second_shipment.id,
                                                           relationships={
                                                               'tags': AssertionHelper.EntityRef(
                                                                   resource='ShipmentTag', pk=shipment_tags[1].id)
                                                           })
                             ],
                             included=[
                                 AssertionHelper.EntityRef(resource='ShipmentTag',
                                                           pk=str(shipment_tags[0].id),
                                                           attributes={
                                                               'tag_type': shipment_tags[0].tag_type,
                                                               'tag_value': shipment_tags[0].tag_value
                                                           }),
                                 AssertionHelper.EntityRef(resource='ShipmentTag',
                                                           pk=str(shipment_tags[1].id),
                                                           attributes={
                                                               'tag_type': shipment_tags[1].tag_type,
                                                               'tag_value': shipment_tags[1].tag_value
                                                           })
                             ])

    # Test case insensitive shipment filter by tag_type, should return one entity.
    response = client_alice.get(f'{shipment_list_url}?tag_type={shipment_tag_creation_data["tag_type"].upper()}')
    AssertionHelper.HTTP_200(response,
                             is_list=True,
                             entity_refs=AssertionHelper.EntityRef(resource='Shipment',
                                                                   pk=shipment.id,
                                                                   relationships={
                                                                      'tags': AssertionHelper.EntityRef(
                                                                          resource='ShipmentTag', pk=shipment_tags[0].id)
                                                                   }),
                             included=AssertionHelper.EntityRef(resource='ShipmentTag',
                                                                pk=str(shipment_tags[0].id),
                                                                attributes={
                                                                    'tag_type': shipment_tags[0].tag_type,
                                                                    'tag_value': shipment_tags[0].tag_value
                                                                })
                             )

    # Test case insensitive shipment filter by tag_value, should return one entity.
    response = client_alice.get(f'{shipment_list_url}?tag_value={shipment_tag_location["tag_value"].upper()}')
    AssertionHelper.HTTP_200(response,
                             is_list=True,
                             entity_refs=AssertionHelper.EntityRef(resource='Shipment',
                                                                   pk=second_shipment.id,
                                                                   relationships={
                                                                      'tags': AssertionHelper.EntityRef(
                                                                         resource='ShipmentTag', pk=shipment_tags[1].id)
                                                                   }),
                             included=AssertionHelper.EntityRef(resource='ShipmentTag',
                                                                pk=str(shipment_tags[1].id),
                                                                attributes={
                                                                    'tag_type': shipment_tags[1].tag_type,
                                                                    'tag_value': shipment_tags[1].tag_value
                                                                })
                             )

    # Test search shipment through tag fields, should return one entity.
    response = client_alice.get(f'{shipment_list_url}?search={shipment_tag_location["tag_value"][:4].lower()}')
    AssertionHelper.HTTP_200(response,
                             is_list=True,
                             entity_refs=AssertionHelper.EntityRef(resource='Shipment',
                                                                   pk=second_shipment.id,
                                                                   relationships={
                                                                      'tags': AssertionHelper.EntityRef(
                                                                         resource='ShipmentTag', pk=shipment_tags[1].id)
                                                                   }),
                             included=AssertionHelper.EntityRef(resource='ShipmentTag',
                                                                pk=str(shipment_tags[1].id),
                                                                attributes={
                                                                    'tag_type': shipment_tags[1].tag_type,
                                                                    'tag_value': shipment_tags[1].tag_value
                                                                })
                             )
