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
import json
from datetime import datetime, timedelta

import pytest
from django.conf import settings
from django.core import mail
from django.urls import reverse
from rest_framework import status
from shipchain_common.test_utils import AssertionHelper, create_form_content

from apps.shipments.models import PermissionLink


class TestPermissionLinkCreate:
    @pytest.fixture(autouse=True)
    def set_up(self, shipment_alice, entity_ref_shipment_alice):
        self.url_permission_link_create = reverse('shipment-permissions-list',
                                                  kwargs={'version': 'v1', 'shipment_pk': shipment_alice.id})
        self.shipment_alice = shipment_alice
        self.shipment_alice_relationships = [{'shipment': entity_ref_shipment_alice}]

    @pytest.fixture
    def mock_aws_failure(self, http_pretty):
        http_pretty.register_uri(http_pretty.POST, settings.URL_SHORTENER_URL + '/',
                                 status=status.HTTP_400_BAD_REQUEST,
                                 body=json.dumps({"message": "Failure in AWS IoT Call."}))

        return http_pretty

    @pytest.fixture
    def mock_aws_success(self, http_pretty):
        http_pretty.register_uri(http_pretty.POST, settings.URL_SHORTENER_URL + '/',
                                 status=status.HTTP_201_CREATED,
                                 body=json.dumps({
                                     "analytics": {
                                         "user_agent": "PostmanRuntime/7.17.1",
                                         "source_ip": "000.000.00.000, 11.11.11.111",
                                         "xray_trace_id": "Root=1-435345"
                                     },
                                     "created_at": "2020-01-14T20:33:36.423300+0000",
                                     "long_url": "https://www.exampleofaverylongurl.com",
                                     "short_id": "d5a4d80195",
                                     "short_url": f"{settings.URL_SHORTENER_URL}/d5a4d80195",
                                     "ttl": 1579638816
                                 }))

        return http_pretty

    def test_requires_access(self, api_client, mock_non_wallet_owner_calls):
        response = api_client.post(self.url_permission_link_create, {'name': 'Permission Link Name'})
        AssertionHelper.HTTP_403(response)

        # TODO: Assert URL calls on httpretty

    def test_can_create_with_permission(self, api_client, mock_successful_wallet_owner_calls):
        response = api_client.post(self.url_permission_link_create, {'name': 'Permission Link Name'})
        AssertionHelper.HTTP_201(response,
                                 entity_refs=AssertionHelper.EntityRef(
                                     resource='PermissionLink',
                                     attributes={'name': 'Permission Link Name'},
                                     relationships=self.shipment_alice_relationships
                                 ))

        # TODO: Assert URL calls on httpretty

    def test_owner_can_create(self, client_alice):
        response = client_alice.post(self.url_permission_link_create, {'name': 'Permission Link Name'})
        AssertionHelper.HTTP_201(response,
                                 entity_refs=AssertionHelper.EntityRef(
                                     resource='PermissionLink',
                                     attributes={'name': 'Permission Link Name'},
                                     relationships=self.shipment_alice_relationships
                                 ))

    def test_requires_valid_expiration_date(self, client_alice):
        response = client_alice.post(self.url_permission_link_create,
                                     {'name': 'Permission Link Name',
                                      'expiration_date': datetime.utcnow() - timedelta(days=1)})

        AssertionHelper.HTTP_400(response, error='The expiration date should be greater than actual date',
                                 pointer='expiration_date')

    def test_valid_expiration_date(self, client_alice):
        attributes = {'name': 'Permission Link Name', 'expiration_date': datetime.utcnow() + timedelta(days=1)}
        response = client_alice.post(self.url_permission_link_create, attributes)

        attributes['expiration_date'] = attributes['expiration_date'].isoformat() + 'Z'
        AssertionHelper.HTTP_201(response,
                                 entity_refs=AssertionHelper.EntityRef(
                                     resource='PermissionLink',
                                     attributes=attributes,
                                     relationships=self.shipment_alice_relationships
                                 ))

    def test_permission_link_requires_aws(self, client_alice, mock_aws_failure):
        response = client_alice.post(self.url_permission_link_create,
                                     {'name': 'Permission Link Name',
                                      'emails': ['test@example.com', 'guest@example.com']})
        AssertionHelper.HTTP_500(response, error='Failure in AWS IoT Call')
        assert len(mail.outbox) == 0

        # TODO: Assert URL calls on httpretty

    def test_permission_link_email_validation(self, client_alice):
        response = client_alice.post(self.url_permission_link_create,
                                     {'name': 'Permission Link Name',
                                      'emails': ['not an email', 'guest@example.com']})
        AssertionHelper.HTTP_400(response, error='Enter a valid email address.',
                                 pointer='emails')

    def test_permission_link_email_send(self, client_alice, mock_aws_success, user_alice):
        response = client_alice.post(self.url_permission_link_create,
                                     {'name': 'Permission Link Name',
                                      'emails': ['test@example.com', 'guest@example.com']})
        AssertionHelper.HTTP_201(response,
                                 entity_refs=AssertionHelper.EntityRef(
                                     resource='PermissionLink',
                                     attributes={'name': 'Permission Link Name'},
                                     relationships=self.shipment_alice_relationships
                                 ))

        assert len(mail.outbox) == 1
        assert 'The ShipChain team' in str(mail.outbox[0].body)
        assert user_alice.username in str(mail.outbox[0].body)
        assert user_alice.username in str(mail.outbox[0].subject)

        # TODO: Assert URL calls on httpretty

    def test_permission_link_email_send_with_expiration(self, client_alice, mock_aws_success, user_alice):
        response = client_alice.post(self.url_permission_link_create,
                                     {'name': 'Permission Link Name',
                                      'emails': ['test@example.com', 'guest@example.com'],
                                      'expiration_date': datetime.utcnow() + timedelta(days=1)})
        AssertionHelper.HTTP_201(response,
                                 entity_refs=AssertionHelper.EntityRef(
                                     resource='PermissionLink',
                                     attributes={
                                         'name': 'Permission Link Name',
                                         'expiration_date': (datetime.utcnow() + timedelta(days=1)).isoformat() + 'Z'},
                                     relationships=self.shipment_alice_relationships
                                 ))

        assert len(mail.outbox) == 1
        assert 'The ShipChain team' in str(mail.outbox[0].body)
        assert user_alice.username in str(mail.outbox[0].body)
        assert user_alice.username in str(mail.outbox[0].subject)

        # TODO: Assert URL calls on httpretty

    def test_permission_link_email_wallet_owner(self, client_bob, mock_aws_success, user_bob,
                                                mock_successful_wallet_owner_calls):
        response = client_bob.post(self.url_permission_link_create,
                                     {'name': 'Permission Link Name',
                                      'emails': ['test@example.com', 'guest@example.com'],
                                      'expiration_date': datetime.utcnow() + timedelta(days=1)})
        AssertionHelper.HTTP_201(response,
                                 entity_refs=AssertionHelper.EntityRef(
                                     resource='PermissionLink',
                                     attributes={
                                         'name': 'Permission Link Name',
                                         'expiration_date': (datetime.utcnow() + timedelta(days=1)).isoformat() + 'Z'},
                                     relationships=self.shipment_alice_relationships
                                 ))

        assert len(mail.outbox) == 1
        assert 'The ShipChain team' in str(mail.outbox[0].body)
        assert user_bob.username in str(mail.outbox[0].body)
        assert user_bob.username in str(mail.outbox[0].subject)

        # TODO: Assert URL calls on httpretty

    def test_permission_link_email_send_multiform(self, client_alice, mock_aws_success, user_alice):
        multi_form_data, content_type = create_form_content({'name': 'Permission Link Name',
                                                             'emails': ['test@example.com', 'guest@example.com']})
        response = client_alice.post(self.url_permission_link_create, multi_form_data, content_type=content_type)
        AssertionHelper.HTTP_201(response,
                                 entity_refs=AssertionHelper.EntityRef(
                                     resource='PermissionLink',
                                     attributes={'name': 'Permission Link Name'},
                                     relationships=self.shipment_alice_relationships
                                 ))

        assert len(mail.outbox) == 1
        assert 'The ShipChain team' in str(mail.outbox[0].body)
        assert user_alice.username in str(mail.outbox[0].body)
        assert user_alice.username in str(mail.outbox[0].subject)

        # TODO: Assert URL calls on httpretty


class TestPermissionLinkShipmentAccess:
    @pytest.fixture(autouse=True)
    def set_up(self, entity_ref_shipment_alice, url_shipment_alice, permission_link_expired,
               permission_link_shipment_alice, url_shipment_alice_two):
        self.entity_ref_shipment_alice = entity_ref_shipment_alice
        self.url_valid_permission = f'{url_shipment_alice}?permission_link={permission_link_shipment_alice.id}'
        self.url_expired_permission = f'{url_shipment_alice}?permission_link={permission_link_expired.id}'
        self.url_wrong_permission = f'{url_shipment_alice_two}?permission_link={permission_link_shipment_alice.id}'
        self.url_shipment_list = f"{reverse('shipment-list', kwargs={'version': 'v1'})}" \
                                 f"?permission_link={permission_link_shipment_alice.id}"

    def test_can_access_without_ownership(self, api_client, mock_non_wallet_owner_calls):
        response = api_client.get(self.url_valid_permission)
        AssertionHelper.HTTP_200(response, entity_refs=self.entity_ref_shipment_alice)

    def test_can_access_with_ownership(self, api_client, mock_successful_wallet_owner_calls):
        response = api_client.get(self.url_valid_permission)
        AssertionHelper.HTTP_200(response, entity_refs=self.entity_ref_shipment_alice)

    def test_shipment_owner_access(self, client_alice):
        response = client_alice.get(self.url_valid_permission)
        AssertionHelper.HTTP_200(response, entity_refs=self.entity_ref_shipment_alice)

    def test_shipment_owner_access_expired_link(self, client_alice):
        response = client_alice.get(self.url_expired_permission)
        AssertionHelper.HTTP_200(response, entity_refs=self.entity_ref_shipment_alice)

    def test_wallet_owner_access_expired_link(self, api_client, mock_successful_wallet_owner_calls):
        response = api_client.get(self.url_expired_permission)
        AssertionHelper.HTTP_200(response, entity_refs=self.entity_ref_shipment_alice)

    def test_non_owner_expired_link_fails(self, api_client, mock_non_wallet_owner_calls):
        response = api_client.get(self.url_expired_permission)
        AssertionHelper.HTTP_403(response)

    def test_cannot_delete_with_permission_link(self, api_client, mock_non_wallet_owner_calls):
        response = api_client.delete(self.url_valid_permission)
        AssertionHelper.HTTP_403(response)

    def test_owner_can_delete_with_permission_link(self, client_alice):
        response = client_alice.delete(self.url_valid_permission)
        AssertionHelper.HTTP_204(response)

    def test_cannot_update_with_permission_link(self, api_client, mock_non_wallet_owner_calls):
        response = api_client.patch(self.url_valid_permission, {'carrier_scac': 'carrier_scac'})
        AssertionHelper.HTTP_403(response)

    def test_owner_can_update_with_permission_link(self, client_alice):
        response = client_alice.patch(self.url_valid_permission, {'carriers_scac': 'carriers_scac'})
        self.entity_ref_shipment_alice.attributes = {'carriers_scac': 'carriers_scac'}

        AssertionHelper.HTTP_202(response, entity_refs=self.entity_ref_shipment_alice)

    def test_requires_shipment_relationship(self, api_client, mock_non_wallet_owner_calls):
        response = api_client.get(self.url_wrong_permission)
        AssertionHelper.HTTP_403(response)

    def test_owner_wrong_permission(self, client_alice, entity_ref_shipment_alice_two):
        response = client_alice.get(self.url_wrong_permission)
        AssertionHelper.HTTP_200(response, entity_refs=entity_ref_shipment_alice_two)

    def test_cannot_list_with_permission(self, api_client):
        response = api_client.get(self.url_shipment_list)
        AssertionHelper.HTTP_403(response)


class TestPermissionDetail:
    def test_owner_can_delete(self, client_alice, url_permission_link_detail):
        response = client_alice.delete(url_permission_link_detail)
        AssertionHelper.HTTP_204(response)

    def test_wallet_owners_can_delete(self, api_client, url_permission_link_detail, mock_successful_wallet_owner_calls):
        response = api_client.delete(url_permission_link_detail)
        AssertionHelper.HTTP_204(response)

    def test_owner_cannot_retrieve(self, client_alice, url_permission_link_detail):
        response = client_alice.get(url_permission_link_detail)
        AssertionHelper.HTTP_405(response, error='Method "GET" not allowed.')

    def test_owner_cannot_update(self, client_alice, url_permission_link_detail):
        response = client_alice.patch(url_permission_link_detail,
                                      {'expiration_date': datetime.utcnow() + timedelta(days=1)})
        AssertionHelper.HTTP_405(response, error='Method "PATCH" not allowed.')


class TestPermissionList:
    @pytest.fixture(autouse=True)
    def set_up(self, entity_ref_permission_link, entity_ref_permission_link_expired, shipment_alice,
               shipment_alice_two):
        self.entity_refs = [entity_ref_permission_link, entity_ref_permission_link_expired]
        self.list_url = reverse('shipment-permissions-list', kwargs={'version': 'v1', 'shipment_pk': shipment_alice.id})
        self.list_url_two = reverse('shipment-permissions-list',
                                    kwargs={'version': 'v1', 'shipment_pk': shipment_alice_two.id})
        self.shipment_alice = shipment_alice
        self.shipment_alice_two = shipment_alice_two

    def test_owner_can_list(self, client_alice):
        response = client_alice.get(self.list_url)
        AssertionHelper.HTTP_200(response, entity_refs=self.entity_refs, is_list=True,
                                 count=PermissionLink.objects.filter(shipment=self.shipment_alice).count())

    def test_list_depends_on_shipment(self, client_alice):
        response = client_alice.get(self.list_url_two)
        AssertionHelper.HTTP_200(response, entity_refs=[], is_list=True,
                                 count=PermissionLink.objects.filter(shipment=self.shipment_alice_two).count())

        assert PermissionLink.objects.filter(shipment=self.shipment_alice).count() == 2

    def test_wallet_owner_can_list(self, api_client, mock_successful_wallet_owner_calls):
        response = api_client.get(self.list_url)
        AssertionHelper.HTTP_200(response, entity_refs=self.entity_refs, is_list=True,
                                 count=PermissionLink.objects.filter(shipment=self.shipment_alice).count())
