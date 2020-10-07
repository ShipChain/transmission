import json
from django.conf import settings
from django.urls import reverse
from pytest import fixture
from rest_framework import status
from shipchain_common.test_utils import AssertionHelper

from apps.shipments.models import AccessRequest, PermissionLevel, Endpoints, TrackingData


@fixture
def access_request_ro_attributes():
    return {
        'shipment_permission': PermissionLevel.READ_ONLY.name,
        'tags_permission': PermissionLevel.READ_ONLY.name,
        'documents_permission': PermissionLevel.READ_ONLY.name,
        'notes_permission': PermissionLevel.READ_ONLY.name,
        'tracking_permission': PermissionLevel.READ_ONLY.name,
        'telemetry_permission': PermissionLevel.READ_ONLY.name,
    }

@fixture
def access_request_rw_attributes():
    return {
        'shipment_permission': PermissionLevel.READ_WRITE.name,
        'tags_permission': PermissionLevel.READ_WRITE.name,
        'documents_permission': PermissionLevel.READ_WRITE.name,
        'notes_permission': PermissionLevel.READ_WRITE.name,
        'tracking_permission': PermissionLevel.READ_ONLY.name,
        'telemetry_permission': PermissionLevel.READ_ONLY.name,
    }


@fixture
def new_access_request_bob(shipment_alice, user_bob, access_request_ro_attributes):
    return AccessRequest.objects.create(shipment=shipment_alice, requester_id=user_bob.id, **access_request_ro_attributes)

@fixture
def new_rw_access_request_bob(shipment_alice, user_bob, access_request_rw_attributes):
    return AccessRequest.objects.create(shipment=shipment_alice, requester_id=user_bob.id, **access_request_rw_attributes)

@fixture
def approved_access_request_bob(new_access_request_bob):
    new_access_request_bob.approved = True
    new_access_request_bob.save()
    return new_access_request_bob

@fixture
def new_access_request_lionel(shipment_alice, user_lionel, access_request_ro_attributes):
    return AccessRequest.objects.create(shipment=shipment_alice, requester_id=user_lionel.id, **access_request_ro_attributes)

@fixture
def approved_access_request_lionel(new_access_request_lionel):
    new_access_request_lionel.approved = True
    new_access_request_lionel.save()
    return new_access_request_lionel

@fixture
def entity_ref_access_request_bob(new_access_request_bob, user_bob_id, entity_ref_shipment_alice):
    return AssertionHelper.EntityRef(resource='AccessRequest', pk=new_access_request_bob.id,
                                     attributes={'requester_id': user_bob_id},
                                     relationships=[{'shipment': entity_ref_shipment_alice}])


class TestAccessRequestCreation:
    @fixture(autouse=True)
    def setup_urls(self, shipment_alice):
        self.list_url = reverse('shipment-access-requests-list', kwargs={'version': 'v1', 'shipment_pk': shipment_alice.id})

    def test_requires_authentication(self, api_client):
        response = api_client.post(self.list_url)
        AssertionHelper.HTTP_403(response)

    # Validate that you can't request all NONE permissions (which would be a noop)
    def test_cant_request_no_permissions(self, client_bob):
        # All permissions default to NONE so a blank request should be rejected
        response = client_bob.post(self.list_url)
        AssertionHelper.HTTP_400(response, 'Access requests must contain at least one requested permission')

        # A request that explicitly requests all NONE permissions should also be rejected
        response = client_bob.post(self.list_url, {
            'shipment_permission': PermissionLevel.NONE.name,
            'tags_permission': PermissionLevel.NONE.name,
            'documents_permission': PermissionLevel.NONE.name,
            'notes_permission': PermissionLevel.NONE.name,
            'tracking_permission': PermissionLevel.NONE.name,
            'telemetry_permission': PermissionLevel.NONE.name
        })
        AssertionHelper.HTTP_400(response, 'Access requests must contain at least one requested permission')

    # Should not be able to create an access request for a shipment you own
    def test_cant_request_own(self, client_alice, access_request_ro_attributes):
        response = client_alice.post(self.list_url, access_request_ro_attributes)
        AssertionHelper.HTTP_403(response, 'You do not have permission to perform this action.')

    # approved/approved_at/approved_by,requester_id fields are read-only
    def test_ro_fields(self, client_bob, user_alice_id, user_bob_id, access_request_ro_attributes, current_datetime):
        response = client_bob.post(self.list_url, {**access_request_ro_attributes,
                                                     **{'approved': True}})
        AssertionHelper.HTTP_400(response, 'User does not have access to approve this access request')
        response = client_bob.post(self.list_url, {**access_request_ro_attributes,
                                                   **{'approved_at': current_datetime}})
        AssertionHelper.HTTP_201(response, attributes={'approved_at': None})
        response = client_bob.post(self.list_url, {**access_request_ro_attributes,
                                                   **{'approved_by': user_alice_id}})
        AssertionHelper.HTTP_201(response, attributes={'approved_by': None})
        response = client_bob.post(self.list_url, {**access_request_ro_attributes,
                                                   **{'requester_id': user_alice_id}})
        AssertionHelper.HTTP_201(response, attributes={'requester_id': user_bob_id})

    # Any authenticated user should be able to request access for any valid shipment ID (except their own)
    def test_create_access_request(self, shipment_alice, client_bob, access_request_ro_attributes, user_bob_id):
        response = client_bob.post(self.list_url, access_request_ro_attributes)
        AssertionHelper.HTTP_201(response, entity_refs=AssertionHelper.EntityRef(
            resource='AccessRequest',
            attributes={**{'requester_id': user_bob_id}, **access_request_ro_attributes}
        ))

    # Multiple shipment access request creation
    def test_create_multiple_access_requests(self, shipment_alice, client_bob, access_request_ro_attributes, access_request_rw_attributes, user_bob_id):
        response = client_bob.post(self.list_url, access_request_ro_attributes)
        AssertionHelper.HTTP_201(response, entity_refs=AssertionHelper.EntityRef(
            resource='AccessRequest',
            attributes={**{'requester_id': user_bob_id}, **access_request_ro_attributes}
        ))

        response = client_bob.post(self.list_url, access_request_rw_attributes)
        AssertionHelper.HTTP_201(response, entity_refs=AssertionHelper.EntityRef(
            resource='AccessRequest',
            attributes={**{'requester_id': user_bob_id}, **access_request_rw_attributes}
        ))

    # TODO: Shipment owner(s?) should be notified of access requests (email, ???)

    # Tracking and telemetry endpoints should not be able to be requested as RW
    def test_tracking_telemetry_ro(self, shipment_alice, client_bob, access_request_rw_attributes):
        response = client_bob.post(self.list_url, {**access_request_rw_attributes, **{'tracking_permission': PermissionLevel.READ_WRITE.name}})
        AssertionHelper.HTTP_400(response, 'Cannot request write access to this field')

        response = client_bob.post(self.list_url, {**access_request_rw_attributes, **{'telemetry_permission': PermissionLevel.READ_WRITE.name}})
        AssertionHelper.HTTP_400(response, 'Cannot request write access to this field')

    # No shipment details should be included in the access request creation response
    def test_shipment_not_included(self, shipment_alice, client_bob, access_request_ro_attributes):
        response = client_bob.post(self.list_url, {**access_request_ro_attributes})
        AssertionHelper.HTTP_201(response)
        assert 'included' not in response.json()

    def test_tags_without_shipment(self, shipment_alice, client_bob):
        response = client_bob.post(self.list_url, {'tags_permission': PermissionLevel.READ_ONLY.name})
        AssertionHelper.HTTP_400(response, 'Cannot request to view tags without shipment read access')

class TestAccessRequestUpdate:
    @fixture(autouse=True)
    def setup_urls(self, shipment_alice, new_access_request_bob):
        self.detail_url = reverse('shipment-access-requests-detail', kwargs={'version': 'v1', 'shipment_pk': shipment_alice.id, 'pk': new_access_request_bob.id})

    def test_ro_fields(self, client_alice, client_bob, current_datetime, user_alice_id, user_bob_id, entity_ref_shipment_alice, shipment_bob, access_request_ro_attributes):
        # approved_at/approved_by/requester_id/shipment fields are read-only
        for api_client in (client_alice, client_bob):
            response = api_client.patch(self.detail_url, {**access_request_ro_attributes,
                                                       **{'approved_at': current_datetime}})
            AssertionHelper.HTTP_200(response, attributes={'approved_at': None})
            response = api_client.patch(self.detail_url, {**access_request_ro_attributes,
                                                       **{'approved_by': user_alice_id}})
            AssertionHelper.HTTP_200(response, attributes={'approved_by': None})
            response = api_client.patch(self.detail_url, {**access_request_ro_attributes,
                                                       **{'requester_id': user_alice_id}})
            AssertionHelper.HTTP_200(response, attributes={'requester_id': user_bob_id})
            response = api_client.patch(self.detail_url, {**access_request_ro_attributes,
                                                          **{'shipment_id': shipment_bob.id}})
            AssertionHelper.HTTP_200(response, relationships={'shipment': entity_ref_shipment_alice})

    # Validate that you can't request all NONE permissions (which would be a noop)
    def test_cant_request_no_permissions(self, client_bob):
        response = client_bob.patch(self.detail_url, {
            'shipment_permission': PermissionLevel.NONE.name,
            'tags_permission': PermissionLevel.NONE.name,
            'documents_permission': PermissionLevel.NONE.name,
            'notes_permission': PermissionLevel.NONE.name,
            'tracking_permission': PermissionLevel.NONE.name,
            'telemetry_permission': PermissionLevel.NONE.name
        })
        AssertionHelper.HTTP_400(response, 'Access requests must contain at least one requested permission')

    # Only Shipment 'owners' can approve an access request
    def test_approver_permission(self, client_alice, client_bob, access_request_ro_attributes):
        response = client_bob.patch(self.detail_url, {'approved': True, **access_request_ro_attributes})
        AssertionHelper.HTTP_400(response, 'User does not have access to approve this access request')

        response = client_alice.patch(self.detail_url, {'approved': True, **access_request_ro_attributes})
        AssertionHelper.HTTP_200(response, attributes={'approved': True})

    # No one can change already-approved AccessRequest permissions
    def test_approved_permissions_immutability(self, approved_access_request_bob, client_alice, client_bob, access_request_rw_attributes):
        assert approved_access_request_bob.approved is True
        for api_client in (client_alice, client_bob):
            response = api_client.patch(self.detail_url, access_request_rw_attributes)
            AssertionHelper.HTTP_400(response, 'Cannot modify the permission level of an approved access request')

    # Test approving and modifying access request in the same request
    def test_cannot_approve_and_modify(self, new_access_request_bob, client_alice, access_request_rw_attributes):
        response = client_alice.patch(self.detail_url, {'approved': True, **access_request_rw_attributes})
        AssertionHelper.HTTP_400(response, 'Only the requester can modify permissions in a pending or denied access request')

    # Only the requester can modify the requested permissions in a pending access request
    def test_pending_permissions_mutability(self, new_access_request_bob, client_alice, client_bob, access_request_rw_attributes):
        assert new_access_request_bob.approved is None

        response = client_alice.patch(self.detail_url, access_request_rw_attributes)
        AssertionHelper.HTTP_400(response, 'Only the requester can modify permissions in a pending or denied access request')

        response = client_bob.patch(self.detail_url, access_request_rw_attributes)
        AssertionHelper.HTTP_200(response, attributes=access_request_rw_attributes)

    # During approval, the full list of approved permissions MUST be sent from the approval as part of the API request
    # (a race condition exists where an approver can have already 'loaded' the request, but the requester changes it right before approval)
    def test_permissions_confirmation_required(self, new_access_request_bob, client_alice, access_request_ro_attributes):
        assert new_access_request_bob.approved is None

        response = client_alice.patch(self.detail_url, {'approved': True})
        AssertionHelper.HTTP_400(response, 'Full list of permissions must be passed in request for approval')

        response = client_alice.patch(self.detail_url, {'approved': True, **access_request_ro_attributes})
        AssertionHelper.HTTP_200(response, attributes=access_request_ro_attributes)

    # TODO: Approval/denial should send notifications to the requester

    # A requester can modify a denied accessrequest, which will clear the approved flag and resend a notification for further review
    def test_rerequest_denied(self, new_access_request_bob, client_bob, access_request_ro_attributes):
        new_access_request_bob.approved = False
        new_access_request_bob.save()

        response = client_bob.patch(self.detail_url, {'shipment_permission': PermissionLevel.READ_WRITE.name})
        AssertionHelper.HTTP_200(response, attributes={**access_request_ro_attributes, **{'shipment_permission': PermissionLevel.READ_WRITE.name, 'approved': None}})

        new_access_request_bob.refresh_from_db()
        assert new_access_request_bob.approved is None

        # TODO: assert notification is resent to approver

    # Shipment owner can revoke an access request by changing the approval to False
    def test_permissions_revocation(self, approved_access_request_bob, client_alice, client_bob):
        assert approved_access_request_bob.approved is True

        response = client_alice.patch(self.detail_url, {'approved': False})
        AssertionHelper.HTTP_200(response, attributes={'approved': False})

    # Should not be able to delete an access request
    def test_deletion(self, new_access_request_bob, client_alice, client_bob):
        response = client_alice.delete(self.detail_url)
        AssertionHelper.HTTP_405(response)

        response = client_bob.delete(self.detail_url)
        AssertionHelper.HTTP_405(response)

    # Tracking and telemetry endpoints should not be able to be updated as RW
    def test_tracking_telemetry_ro(self, shipment_alice, client_bob, new_access_request_bob, access_request_rw_attributes):
        response = client_bob.patch(self.detail_url, {'tracking_permission': PermissionLevel.READ_WRITE.name})
        AssertionHelper.HTTP_400(response, 'Cannot request write access to this field')

        response = client_bob.patch(self.detail_url, {'telemetry_permission': PermissionLevel.READ_WRITE.name})
        AssertionHelper.HTTP_400(response, 'Cannot request write access to this field')

    def test_tags_without_shipment(self, shipment_alice, client_bob):
        response = client_bob.patch(self.detail_url, {
            'shipment_permission': PermissionLevel.NONE.name,
            'tags_permission': PermissionLevel.READ_WRITE.name
        })
        AssertionHelper.HTTP_400(response, 'Cannot request to view tags without shipment read access')


class TestAccessRequestRetrieval:
    @fixture(autouse=True)
    def setup_urls(self, shipment_alice):
        self.list_url = reverse('access-requests-list', kwargs={'version': 'v1'})
        self.shipment_list_url = reverse('shipment-access-requests-list', kwargs={'version': 'v1', 'shipment_pk': shipment_alice.id})

    # Shipment owners should be able to see full list of shipment access requests
    def test_get_list(self, client_alice, entity_ref_access_request_bob):
        response = client_alice.get(self.shipment_list_url)
        AssertionHelper.HTTP_200(response, is_list=True, entity_refs=[entity_ref_access_request_bob], count=1)

    # Access requests should be able to be filtered by approval status
    def test_filtering(self, client_alice, new_access_request_bob):
        response = client_alice.get(self.shipment_list_url + '?approved=true')
        AssertionHelper.HTTP_200(response, is_list=True, count=0)

    # Other authenticated users can only see ones that they've created (but for any shipment, GET /shipments/access_requests)
    def test_get_requester_list(self, client_bob, client_lionel, entity_ref_access_request_bob):
        response = client_bob.get(self.list_url)
        AssertionHelper.HTTP_200(response, is_list=True, entity_refs=[entity_ref_access_request_bob], count=1)

        response = client_bob.get(self.shipment_list_url)
        AssertionHelper.HTTP_200(response, is_list=True, entity_refs=[entity_ref_access_request_bob], count=1)

        response = client_lionel.get(self.list_url)
        AssertionHelper.HTTP_200(response, is_list=True, count=0)

        response = client_lionel.get(self.shipment_list_url)
        AssertionHelper.HTTP_200(response, is_list=True, count=0)

    # Ensure requester's pending access requests list does not include any unauthorized shipment details
    def test_shipment_not_included(self, client_bob, new_access_request_bob):
        response = client_bob.get(self.list_url)
        AssertionHelper.HTTP_200(response, is_list=True, count=1)
        assert 'included' not in response.json()

        response = client_bob.get(self.shipment_list_url)
        AssertionHelper.HTTP_200(response, is_list=True, count=1)
        assert 'included' not in response.json()

class TestAccessRequestPermissions:
    @fixture(autouse=True)
    def setup_urls(self, shipment_alice, mock_non_wallet_owner_calls, devices):
        self.list_url = reverse('access-requests-list', kwargs={'version': 'v1'})
        self.endpoint_urls = {endpoint.name: reverse(f'shipment-{endpoint.name}-list', kwargs={'version': 'v1', 'shipment_pk': shipment_alice.id})
                              for endpoint in Endpoints if endpoint.name not in ('shipment', 'tracking')}
        self.endpoint_urls['shipment'] = reverse('shipment-detail', kwargs={'version': 'v1', 'pk': shipment_alice.id})
        self.endpoint_urls['tracking'] = reverse('shipment-tracking', kwargs={'version': 'v1', 'pk': shipment_alice.id})

        shipment_alice.device = devices[0]
        shipment_alice.save()
        mock_non_wallet_owner_calls.register_uri(
            mock_non_wallet_owner_calls.GET,
            f'{settings.PROFILES_URL}/api/v1/device/{shipment_alice.device.id}/sensor',
            body=json.dumps({"links": {
                "first": f"{settings.PROFILES_URL}/api/v1/device/",
                "last": f"{settings.PROFILES_URL}/api/v1/device/",
                "next": None,
            }, "data": [{}]}),
            status=status.HTTP_200_OK)
        self.endpoint_urls['sensors'] = reverse('device-sensors', kwargs={'version': 'v1', 'device_pk': shipment_alice.device.id})

        self.tag = shipment_alice.shipment_tags.create(owner_id=shipment_alice.owner_id, tag_type='tag_type', tag_value='tag_value')

    def assert_read_access(self, client, shipment_access=None, tags_access=None, documents_access=None, notes_access=None, tracking_access=None, telemetry_access=None, all_access=None):
        if all_access is not None:
            shipment_access = all_access
            tags_access = all_access
            documents_access = all_access
            notes_access = all_access
            tracking_access = all_access
            telemetry_access = all_access

        if documents_access is not None:
            response = client.get(self.endpoint_urls['documents'])
            AssertionHelper.HTTP_200(response, is_list=True) if documents_access else AssertionHelper.HTTP_403(response)

        if notes_access is not None:
            response = client.get(self.endpoint_urls['notes'])
            AssertionHelper.HTTP_200(response, is_list=True) if notes_access else AssertionHelper.HTTP_403(response)

        if tracking_access is not None:
            response = client.get(self.endpoint_urls['tracking'])
            AssertionHelper.HTTP_200(response) if tracking_access else AssertionHelper.HTTP_403(response)

        if shipment_access is not None:
            response = client.get(self.endpoint_urls['shipment'])
            AssertionHelper.HTTP_200(response) if shipment_access else AssertionHelper.HTTP_403(response)

        if tags_access is not None:
            # Tags are a special case, do not have list/retrieve, only visible via shipment model
            response = client.get(self.endpoint_urls['shipment'])
            if tags_access:
                AssertionHelper.HTTP_200(response,
                                         entity_refs=AssertionHelper.EntityRef(resource='Shipment', relationships={
                                             'tags': AssertionHelper.EntityRef(resource='ShipmentTag',
                                                                               pk=self.tag.id)}),
                                         included=AssertionHelper.EntityRef(resource='ShipmentTag'), )
            elif response.status_code == 200:
                # Can only see tags if the user also has shipment access
                assert 'tags' not in response.json()['data']['relationships']
                for included in response.json()['included']:
                    assert included['type'] != 'ShipmentTag'

        if telemetry_access is not None:
            # Telemetry endpoint is not JSON API format
            response = client.get(self.endpoint_urls['telemetry'])
            if telemetry_access:
                assert response.status_code == 200
                assert response.json() == []
            else:
                assert response.status_code == 403

            # Should also have access to sensors endpoint
            response = client.get(self.endpoint_urls['sensors'])
            if telemetry_access:
                AssertionHelper.HTTP_200(response, is_list=True)
            else:
                AssertionHelper.HTTP_403(response, vnd=False)

    def assert_write_access(self, client, shipment_access=None, tags_access=None, documents_access=None, notes_access=None, all_access=None):
        if all_access is not None:
            shipment_access = all_access
            tags_access = all_access
            documents_access = all_access
            notes_access = all_access

        shipment_data = {'carriers_scac': 'h4x3d'}
        tag_data = {
            'tag_type': 'foo',
            'tag_value': 'bar',
            'owner_id': client.handler._force_user.id,
        }
        document_data = {
            'name': 'Test BOL',
            'file_type': 'PDF',
            'document_type': 'AIR_WAYBILL'
        }
        note_data = {'message': 'hello, world.'}

        if shipment_access is not None:
            response = client.patch(self.endpoint_urls['shipment'], shipment_data)
            AssertionHelper.HTTP_202(response) if shipment_access else AssertionHelper.HTTP_403(response)

        if tags_access is not None:
            response = client.post(self.endpoint_urls['tags'], tag_data)
            AssertionHelper.HTTP_201(response) if tags_access else AssertionHelper.HTTP_403(response)

        if documents_access is not None:
            response = client.post(self.endpoint_urls['documents'], document_data)
            AssertionHelper.HTTP_201(response) if documents_access else AssertionHelper.HTTP_403(response)

        if notes_access is not None:
            response = client.post(self.endpoint_urls['notes'], note_data)
            AssertionHelper.HTTP_201(response) if notes_access else AssertionHelper.HTTP_403(response)


    # Bob (org 2) should not have access to Alice's (org 1) shipment
    def test_no_shipment_access(self, shipment_alice, client_bob):
        # Test R
        self.assert_read_access(client_bob, all_access=False)

        # Test W
        self.assert_write_access(client_bob, all_access=False)

    # Bob's unapproved request should not grant him any permissions to Alice's shipment
    def test_no_unapproved_shipment_access(self, shipment_alice, client_bob, new_access_request_bob):
        # Test R
        self.assert_read_access(client_bob, all_access=False)

        # Test W
        self.assert_write_access(client_bob, all_access=False)


    # Bob's approved request should grant him all of the permissions (at the appropriate level) included in his request
    def test_approved_access(self, shipment_alice, client_bob, approved_access_request_bob, access_request_rw_attributes):
        # Test RO gives R
        self.assert_read_access(client_bob, all_access=True)

        # Test RO does not give W
        self.assert_write_access(client_bob, all_access=False)

        # Modify access request to RW
        AccessRequest.objects.filter(id=approved_access_request_bob.id).update(**access_request_rw_attributes)
        approved_access_request_bob.refresh_from_db()

        # Test RW gives R
        self.assert_read_access(client_bob, all_access=True)

        # Test RW gives W
        self.assert_write_access(client_bob, all_access=True)

    # Test that an accessrequest with RW for Shipment but no access for Tags does not return Tags on Shipment update
    def test_rw_shipment_no_tags_on_update(self, shipment_alice, client_bob, new_rw_access_request_bob, entity_ref_shipment_alice):
        new_rw_access_request_bob.tags_permission = PermissionLevel.NONE
        new_rw_access_request_bob.approved = True
        new_rw_access_request_bob.save()

        response = client_bob.patch(self.endpoint_urls['shipment'], {'carriers_scac': 'h4x3d'})
        AssertionHelper.HTTP_202(response, entity_refs=entity_ref_shipment_alice)
        assert 'tags' not in response.json()['data']['relationships']
        for included in response.json()['included']:
            assert included['type'] != 'ShipmentTag'

    # A second, unapproved request should not grant Bob any more permissions to Alice's shipment
    def test_unapproved_request_doesnt_grant_additional_permissions(self, shipment_alice, client_bob, user_bob_id, approved_access_request_bob, access_request_rw_attributes):
        AccessRequest.objects.create(shipment=shipment_alice, requester_id=user_bob_id, **access_request_rw_attributes)
        self.assert_read_access(client_bob, all_access=True)
        self.assert_write_access(client_bob, all_access=False)

    # If Bob has two+ approved requests, he should be granted permissions corresponding to the union of all approved permissions
    def test_two_approved_requests(self, shipment_alice, client_bob, user_bob_id, approved_access_request_bob, access_request_rw_attributes):
        all_rw = AccessRequest.objects.create(shipment=shipment_alice, requester_id=user_bob_id, **access_request_rw_attributes, approved=True)
        self.assert_read_access(client_bob, all_access=True)
        self.assert_write_access(client_bob, all_access=True)
        all_rw.delete()

        AccessRequest.objects.create(shipment=shipment_alice, requester_id=user_bob_id, **{
            'notes_permission': PermissionLevel.READ_WRITE.name,
        }, approved=True)
        self.assert_read_access(client_bob, all_access=True)
        self.assert_write_access(client_bob, notes_access=True, shipment_access=False, tags_access=False, documents_access=False)

    # Requesters should no longer have access to shipment details after revocation
    def test_revocation(self, shipment_alice, client_bob, approved_access_request_bob):
        self.assert_read_access(client_bob, True)
        approved_access_request_bob.approved = False
        approved_access_request_bob.save()
        self.assert_read_access(client_bob, False)

    # For each endpoint permission, test that the permission levels are respected (NONE/READ_ONLY,READ_WRITE)
    def test_endpoint_permission_levels(self, shipment_alice, client_bob, user_bob_id):
        for endpoint in Endpoints:
            permissions = {
                f'{endpoint.name}_permission': PermissionLevel.NONE.name,
            }
            if endpoint == Endpoints.tags:
                # Can't read tags without Shipment access
                permissions['shipment_permission'] = PermissionLevel.READ_ONLY.name

            # NONE
            request = AccessRequest.objects.create(shipment=shipment_alice, requester_id=user_bob_id, **permissions, approved=True)
            self.assert_read_access(client_bob, **{f'{endpoint.name}_access': False})
            if endpoint not in (Endpoints.tracking, Endpoints.telemetry):
                self.assert_write_access(client_bob, **{f'{endpoint.name}_access': False})
            request.delete()

            # READ_ONLY
            permissions[f'{endpoint.name}_permission'] = PermissionLevel.READ_ONLY.name
            request = AccessRequest.objects.create(shipment=shipment_alice, requester_id=user_bob_id, **permissions, approved=True)
            self.assert_read_access(client_bob, **{f'{endpoint.name}_access': True})
            if endpoint not in (Endpoints.tracking, Endpoints.telemetry):
                self.assert_write_access(client_bob, **{f'{endpoint.name}_access': False})
            request.delete()

            # READ_WRITE
            if endpoint not in (Endpoints.tracking, Endpoints.telemetry):
                permissions[f'{endpoint.name}_permission'] = PermissionLevel.READ_WRITE.name
                request = AccessRequest.objects.create(shipment=shipment_alice, requester_id=user_bob_id, **permissions, approved=True)
                self.assert_read_access(client_bob, **{f'{endpoint.name}_access': True})
                self.assert_write_access(client_bob, **{f'{endpoint.name}_access': True})
                request.delete()

    # Permission links grant full RO permission, but should combine with AccessRequests for RW
    def test_with_permission_links(self, shipment_alice, client_bob, new_rw_access_request_bob, permission_link_shipment_alice):
        shipment_data = {'carriers_scac': 'h4x3d'}
        tag_data = {
            'tag_type': 'foo',
            'tag_value': 'bar',
            'owner_id': client_bob.handler._force_user.id,
        }

        # Documents/notes are not accessible via permission link, tracking/telemetry is RO
        response = client_bob.get(f'{self.endpoint_urls["shipment"]}?permission_link={permission_link_shipment_alice.id}')
        AssertionHelper.HTTP_200(response,
                                 entity_refs=AssertionHelper.EntityRef(resource='Shipment', relationships={
                                     'tags': AssertionHelper.EntityRef(resource='ShipmentTag',
                                                                       pk=self.tag.id)}),
                                 included=AssertionHelper.EntityRef(resource='ShipmentTag'), )


        response = client_bob.patch(f'{self.endpoint_urls["shipment"]}?permission_link={permission_link_shipment_alice.id}', shipment_data)
        AssertionHelper.HTTP_403(response)

        response = client_bob.post(f'{self.endpoint_urls["tags"]}?permission_link={permission_link_shipment_alice.id}', tag_data)
        AssertionHelper.HTTP_403(response)

        new_rw_access_request_bob.approved = True
        new_rw_access_request_bob.save()

        response = client_bob.patch(f'{self.endpoint_urls["shipment"]}?permission_link={permission_link_shipment_alice.id}', shipment_data)
        AssertionHelper.HTTP_202(response)

        response = client_bob.post(f'{self.endpoint_urls["tags"]}?permission_link={permission_link_shipment_alice.id}', tag_data)
        AssertionHelper.HTTP_201(response)


    # Test existence of other approved accessrequests for other users on the shipment should not grant access..
    def test_others_approved_access(self, shipment_alice, client_bob, approved_access_request_lionel):
        self.assert_read_access(client_bob, all_access=False)
        self.assert_write_access(client_bob, all_access=False)

class TestAccessRequestShipmentViews:
    @fixture(autouse=True)
    def setup_urls(self, shipment_alice, mock_non_wallet_owner_calls, mocked_profiles_wallet_list):
        self.shipment_list = reverse('shipment-list', kwargs={'version': 'v1'})
        self.shipment_overview = reverse('shipment-overview', kwargs={'version': 'v1'})
        self.shipment_detail = reverse('shipment-detail', kwargs={'version': 'v1', 'pk': shipment_alice.id})

    def setup_devices_and_tracking(self, shipment, device, tracking_data):
        shipment.device = device
        shipment.save()
        for in_bbox_data in tracking_data:
            in_bbox_data['device'] = device
            in_bbox_data['shipment'] = shipment
            TrackingData.objects.create(**in_bbox_data)

    # A shipment should include access info for the authenticated user in the 'meta' section of the JSON API response
    def test_meta_field_presence(self, shipment_alice, client_bob, approved_access_request_bob):
        response = client_bob.get(self.shipment_detail)
        AssertionHelper.HTTP_200(response, entity_refs=AssertionHelper.EntityRef(resource='Shipment',
                                                                                 pk=shipment_alice.id,
                                                                                 meta={'permission_derivation': 'AccessRequest'}))

    # Shipments that have been granted access via access request should show up in Shipment list & overview (delineated by meta flag)
    def test_meta_field_list_and_overview(self, shipment_alice, client_bob, approved_access_request_bob, shipment_bob, devices, overview_tracking_data):
        response = client_bob.get(self.shipment_list)
        AssertionHelper.HTTP_200(response, is_list=True, entity_refs=[
            AssertionHelper.EntityRef(resource='Shipment',
                                      pk=shipment_alice.id,
                                      meta={'permission_derivation': 'AccessRequest'}),
            AssertionHelper.EntityRef(resource='Shipment',
                                      pk=shipment_bob.id,
                                      meta={'permission_derivation': 'OwnerOrPartyOrPermissionLink'})
        ])

        # Add devices and tracking to shipments so they show up in the overview
        self.setup_devices_and_tracking(shipment_alice, devices[0], overview_tracking_data[0])
        self.setup_devices_and_tracking(shipment_bob, devices[1], overview_tracking_data[0])

        response = client_bob.get(self.shipment_overview)
        AssertionHelper.HTTP_200(response, is_list=True, entity_refs=[
            AssertionHelper.EntityRef(
                resource='TrackingData',
                relationships=[{
                    'shipment': AssertionHelper.EntityRef(
                        resource='Shipment',
                        pk=shipment_alice.id,
                        meta={'permission_derivation': 'AccessRequest'}
                    )
                }]
            ),
            AssertionHelper.EntityRef(
                resource='TrackingData',
                relationships=[{
                    'shipment': AssertionHelper.EntityRef(
                        resource='Shipment',
                        pk=shipment_bob.id,
                        meta={'permission_derivation': 'OwnerOrPartyOrPermissionLink'}
                    )
                }]
            )
        ])

    # Test that an accessrequest with RW for Shipment but no access for Tags does not return Tags on Shipment overview
    def test_tags_hidden_from_overview(self, shipment_alice, client_bob, new_rw_access_request_bob, devices, overview_tracking_data):
        new_rw_access_request_bob.tags_permission = PermissionLevel.NONE
        new_rw_access_request_bob.approved = True
        new_rw_access_request_bob.save()

        self.setup_devices_and_tracking(shipment_alice, devices[0], overview_tracking_data[0])
        response = client_bob.get(self.shipment_list)
        AssertionHelper.HTTP_200(response, is_list=True, entity_refs=[
            AssertionHelper.EntityRef(
                resource='TrackingData',
                relationships=[{
                    'shipment': AssertionHelper.EntityRef(
                        resource='Shipment',
                        pk=shipment_alice.id
                    )
                }]
            ),
        ])

        response_json = response.json()
        for included in response_json['included']:
            assert included['type'] != 'ShipmentTag'

