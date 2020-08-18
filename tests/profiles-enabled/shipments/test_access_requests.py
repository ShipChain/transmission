from django.urls import reverse
from pytest import fixture
from shipchain_common.test_utils import AssertionHelper

from apps.shipments.models import AccessRequest, PermissionLevel


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
        'tracking_permission': PermissionLevel.READ_WRITE.name,
        'telemetry_permission': PermissionLevel.READ_WRITE.name,
    }


@fixture
def new_access_request_bob(shipment_alice, user_bob_id, access_request_ro_attributes):
    return AccessRequest.objects.create(shipment=shipment_alice, requester_id=user_bob_id, **access_request_ro_attributes)

@fixture
def approved_access_request_bob(new_access_request_bob):
    new_access_request_bob.approved = True
    new_access_request_bob.save()
    return new_access_request_bob


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
        AssertionHelper.HTTP_400(response)  # TODO: assert error message

        # A request that explicitly requests all NONE permissions should also be rejected
        response = client_bob.post(self.list_url, {
            'shipment_permission': PermissionLevel.NONE.name,
            'tags_permission': PermissionLevel.NONE.name,
            'documents_permission': PermissionLevel.NONE.name,
            'notes_permission': PermissionLevel.NONE.name,
            'tracking_permission': PermissionLevel.NONE.name,
            'telemetry_permission': PermissionLevel.NONE.name
        })
        AssertionHelper.HTTP_400(response)  # TODO: assert error message

    # Should not be able to create an access request for a shipment you own
    def test_cant_request_own(self, client_alice):
        response = client_alice.post(self.list_url, access_request_ro_attributes)
        AssertionHelper.HTTP_403(response)  # TODO assert error message

    # approved/approved_at/approved_by,requester_id fields are read-only
    def test_ro_fields(self, client_bob, user_alice_id, access_request_ro_attributes, current_datetime):
        response = client_bob.post(self.list_url, {**access_request_ro_attributes,
                                                     **{'approved': True}})
        AssertionHelper.HTTP_400(response)  # TODO: assert error message(s)
        response = client_bob.post(self.list_url, {**access_request_ro_attributes,
                                                   **{'approved_at': current_datetime}})
        AssertionHelper.HTTP_400(response)  # TODO: assert error message(s)
        response = client_bob.post(self.list_url, {**access_request_ro_attributes,
                                                   **{'approved_by': user_alice_id}})
        AssertionHelper.HTTP_400(response)  # TODO: assert error message(s)
        response = client_bob.post(self.list_url, {**access_request_ro_attributes,
                                                   **{'requester_id': user_alice_id}})
        AssertionHelper.HTTP_400(response)  # TODO: assert error message(s)

    # Any authenticated user should be able to request access for any valid shipment ID
    def test_create_access_request(self, shipment_alice, client_bob, access_request_ro_attributes, user_bob_id):
        response = client_bob.post(self.list_url, access_request_ro_attributes)
        AssertionHelper.HTTP_201(response, entity_refs=AssertionHelper.EntityRef(
            resource='AccessRequest',
            attributes={**{'requester_id': user_bob_id}, **access_request_ro_attributes}
        ))

    # TODO: Multiple shipment access request creation

    # TODO: Shipment owner(s?) should be notified of access requests (email, ???)

class TestAccessRequestUpdate:
    @fixture(autouse=True)
    def setup_urls(self, shipment_alice, new_access_request_bob):
        self.detail_url = reverse('shipment-access-requests-detail', kwargs={'version': 'v1', 'shipment_pk': shipment_alice.id, 'pk': new_access_request_bob.id})

    def test_ro_fields(self, client_alice, client_bob, current_datetime, user_alice_id, shipment_bob):
        # approved_at/approved_by/requester_id/shipment fields are read-only
        for api_client in (client_alice, client_bob):
            response = api_client.patch(self.detail_url, {**access_request_ro_attributes,
                                                       **{'approved_at': current_datetime}})
            AssertionHelper.HTTP_400(response)  # TODO: assert error message(s)
            response = api_client.patch(self.detail_url, {**access_request_ro_attributes,
                                                       **{'approved_by': user_alice_id}})
            AssertionHelper.HTTP_400(response)  # TODO: assert error message(s)
            response = api_client.patch(self.detail_url, {**access_request_ro_attributes,
                                                       **{'requester_id': user_alice_id}})
            AssertionHelper.HTTP_400(response)  # TODO: assert error message(s)
            response = api_client.patch(self.detail_url, {**access_request_ro_attributes,
                                                          **{'shipment_id': shipment_bob.id}})
            AssertionHelper.HTTP_400(response)  # TODO: assert error message(s)

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
        AssertionHelper.HTTP_400(response)  # TODO: assert error message

    # Only Shipment 'owners' can approve an access request
    def test_approver_permission(self, client_alice, client_bob, access_request_ro_attributes):
        response = client_bob.patch(self.detail_url, {'approved': True, **access_request_ro_attributes})
        AssertionHelper.HTTP_403(response)  # TODO: assert error

        response = client_alice.patch(self.detail_url, {'approved': True, **access_request_ro_attributes})
        AssertionHelper.HTTP_200(response)  # TODO: assert attributes

    # No one can change already-approved AccessRequest permissions
    def test_approved_permissions_immutability(self, approved_access_request_bob, client_alice, client_bob, access_request_rw_attributes):
        assert approved_access_request_bob.approved is True
        for api_client in (client_alice, client_bob):
            response = api_client.patch(self.detail_url, access_request_rw_attributes)
            AssertionHelper.HTTP_400(response)  # TODO: assert error message(s)

    # Only the requester can modify the requested permissions in a pending access request
    def test_pending_permissions_mutability(self, new_access_request_bob, client_alice, client_bob, access_request_rw_attributes):
        assert new_access_request_bob.approved is None

        response = client_alice.patch(self.detail_url, access_request_rw_attributes)
        AssertionHelper.HTTP_403(response)  # TODO: assert attributes

        response = client_bob.patch(self.detail_url, access_request_rw_attributes)
        AssertionHelper.HTTP_200(response)  # TODO: assert attributes

    # During approval, the full list of approved permissions MUST be sent from the approval as part of the API request
    # (a race condition exists where an approver can have already 'loaded' the request, but the requester changes it right before approval)
    def test_permissions_confirmation_required(self, new_access_request_bob, client_alice):
        assert new_access_request_bob.approved is None

        response = client_alice.patch(self.detail_url, {'approved': True})
        AssertionHelper.HTTP_400(response)  # TODO: assert attributes

        response = client_alice.patch(self.detail_url, {'approved': True, **access_request_ro_attributes})
        AssertionHelper.HTTP_200(response)  # TODO: assert attributes

    # TODO: Approval/denial should send notifications to the requester

    # A requester can modify a denied accessrequest, which will clear the approved flag and resend a notification for further review
    def test_rerequest_denied(self, new_access_request_bob, client_bob):
        new_access_request_bob.approved = False
        new_access_request_bob.save()

        response = client_bob.patch(self.detail_url, {'shipment_access': PermissionLevel.READ_WRITE.name})
        AssertionHelper.HTTP_200(response)  # TODO: assert attributes

        new_access_request_bob.refresh_from_db()
        assert new_access_request_bob.approved is None

        # TODO: assert notification is resent to approver

    # Shipment owner can revoke an access request by changing the approval to False
    def test_permissions_revocation(self, approved_access_request_bob, client_alice, client_bob):
        assert approved_access_request_bob.approved is True

        response = client_alice.patch(self.detail_url, {'approved': False})
        AssertionHelper.HTTP_200(response)  # TODO: assert attributes

    # Should not be able to delete an access request
    def test_deletion(self, new_access_request_bob, client_alice, client_bob):
        response = client_alice.delete(self.detail_url, {'approved': False})
        AssertionHelper.HTTP_405(response)


class TestAccessRequestRetrieval:
    @fixture(autouse=True)
    def setup_urls(self, shipment_alice):
        self.list_url = reverse('access-requests-list', kwargs={'version': 'v1'})
        self.shipment_list_url = reverse('shipment-access-requests-list', kwargs={'version': 'v1', 'shipment_pk': shipment_alice.id})

    # Shipment owners should be able to see full list of shipment access requests
    def test_get_list(self, client_alice):
        response = client_alice.get(self.shipment_list_url)
        AssertionHelper.HTTP_200(response)  # TODO: assert attributes

    # Access requests should be able to be filtered by approval status
    def test_filtering(self, client_alice):
        response = client_alice.get(self.shipment_list_url + '?approved=true')
        AssertionHelper.HTTP_200(response)  # TODO: assert attributes and filtering

    # Other authenticated users can only see ones that they've created (but for any shipment, GET /shipments/access_requests)
    def test_get_requester_list(self, client_bob, client_lionel):
        response = client_bob.get(self.list_url)
        AssertionHelper.HTTP_200(response)  # TODO: assert attributes

        response = client_bob.get(self.shipment_list_url)
        AssertionHelper.HTTP_200(response)  # TODO: assert attributes

        response = client_lionel.get(self.shipment_list_url)
        AssertionHelper.HTTP_403(response)  # TODO: assert error

    # Ensure requester's pending access requests list does not include any unauthorized shipment details
    def test_shipment_not_included(self, client_bob):
        response = client_bob.get(self.list_url)
        AssertionHelper.HTTP_200(response)  # TODO: assert that shipment is not included

        response = client_bob.get(self.shipment_list_url)
        AssertionHelper.HTTP_200(response)  # TODO: assert that shipment is not included

class TestAccessRequestPermissions:
    # Bob (org 2) should not have access to Alice's (org 1) shipment

    # Bob's unapproved request should not grant him any permissions to Alice's shipment

    # Bob's approved request should grant him all of the permissions (at the appropriate level) included in his request

    # A second, unapproved request should not grant Bob any more permissions to Alice's shipment

    # If Bob has two+ approved requests, he should be granted permissions corresponding to the union of all approved permissions

    # Requesters should no longer have access to shipment details after revocation

    # For each endpoint permission, test that the permission levels are respected (NONE/READ_ONLY,READ_WRITE)

    # Permission links grant full RO permission, but should combine with AccessRequests for RW
    pass

class TestAccessRequestShipmentViews:
    # A shipment should include access info for the authenticated user in the 'meta' section of the JSON API response

    # Shipments that have been granted access via access request should show up in Shipment list & overview (delineated by meta flag)
    pass
