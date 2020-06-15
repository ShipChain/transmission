from django.urls import reverse
from pytest import fixture, fail
from shipchain_common.test_utils import AssertionHelper


@fixture
def route_attributes():
    return {
        'name': 'Route #1',
    }


class TestRouteCreation:
    url = reverse('shipment-list', kwargs={'version': 'v1'})

    def test_requires_authentication(self, api_client):
        response = api_client.post(self.url)
        AssertionHelper.HTTP_403(response)

    def test_no_attributes(self):
        fail('Test Not Implemented')

    def test_owner_is_caller(self):
        fail('Test Not Implemented')

    def test_with_attributes(self):
        fail('Test Not Implemented')

    def test_with_device_not_authorized_fails(self):
        fail('Test Not Implemented')

    def test_with_unassociated_device(self):
        fail('Test Not Implemented')

    def test_with_device_blocked_on_shipment_fails(self):
        fail('Test Not Implemented')

    def test_with_device_available_on_shipment(self):
        fail('Test Not Implemented')

    def test_with_device_blocked_on_route_fails(self):
        fail('Test Not Implemented')

    def test_with_device_available_on_route(self):
        fail('Test Not Implemented')


class TestRouteUpdate:

    def test_requires_authentication(self):
        fail('Test Not Implemented')

    def test_invalid_route(self):
        fail('Test Not Implemented')

    def test_own(self):
        fail('Test Not Implemented')

    def test_org(self):
        fail('Test Not Implemented')

    def test_other_fails(self):
        fail('Test Not Implemented')

    def test_other_org_fails(self):
        fail('Test Not Implemented')

    def test_remove_device_in_progress_fails(self):
        fail('Test Not Implemented')

    def test_remove_device_not_in_progress(self):
        fail('Test Not Implemented')


class TestRouteDelete:

    def test_requires_authentication(self):
        fail('Test Not Implemented')

    def test_invalid_route(self):
        fail('Test Not Implemented')

    def test_own(self):
        fail('Test Not Implemented')

    def test_org(self):
        fail('Test Not Implemented')

    def test_other_fails(self):
        fail('Test Not Implemented')

    def test_other_org_fails(self):
        fail('Test Not Implemented')

    def test_not_in_progress(self):
        fail('Test Not Implemented')

    def test_in_progress_fails(self):
        fail('Test Not Implemented')

    def test_complete_fails(self):
        fail('Test Not Implemented')


class TestRouteRetrieve:

    def test_requires_authentication(self):
        fail('Test Not Implemented')

    def test_invalid_route(self):
        fail('Test Not Implemented')

    def test_view_own(self):
        fail('Test Not Implemented')

    def test_view_org(self):
        fail('Test Not Implemented')

    def test_view_other_fails(self):
        fail('Test Not Implemented')

    def test_view_other_org_fails(self):
        fail('Test Not Implemented')

    def test_includes_legs(self):
        fail('Test Not Implemented')


class TestRouteAddLeg:

    def test_requires_authentication(self):
        fail('Test Not Implemented')

    def test_invalid_shipment(self):
        fail('Test Not Implemented')

    def test_route_in_progress_fails(self):
        fail('Test Not Implemented')

    def test_route_complete_fails(self):
        fail('Test Not Implemented')

    def test_shipment_in_progress_fails(self):
        fail('Test Not Implemented')

    def test_shipment_complete_fails(self):
        fail('Test Not Implemented')

    def test_shipment_with_device_fails(self):
        fail('Test Not Implemented')

    def test_own_shipment(self):
        fail('Test Not Implemented')

    def test_org_shipment(self):
        fail('Test Not Implemented')

    def test_other_shipment_fails(self):
        fail('Test Not Implemented')

    def test_other_org_shipment_fails(self):
        fail('Test Not Implemented')

    def test_sequence_updates(self):
        fail('Test Not Implemented')


class TestRouteRemoveLeg:

    def test_requires_authentication(self):
        fail('Test Not Implemented')

    def test_invalid_leg(self):
        fail('Test Not Implemented')

    def test_not_yet_started(self):
        fail('Test Not Implemented')

    def test_route_in_progress_fails(self):
        fail('Test Not Implemented')

    def test_route_complete_fails(self):
        fail('Test Not Implemented')

    def test_sequence_recalculated(self):
        fail('Test Not Implemented')
