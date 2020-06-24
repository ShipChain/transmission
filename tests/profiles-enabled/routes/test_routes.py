from unittest import mock

from django.urls import reverse
from pytest import fixture
from rest_framework.exceptions import ValidationError
from shipchain_common.test_utils import AssertionHelper
from shipchain_common.utils import random_id

from apps.routes.models import Route


@fixture
def route_attributes():
    return {
        'name': 'Route #1',
        'driver_id': random_id(),
    }


@fixture
def new_route(org_id_alice):
    return Route.objects.create(owner_id=org_id_alice)


@fixture
def new_route_with_device(org_id_alice, device):
    return Route.objects.create(owner_id=org_id_alice, device=device)


@fixture
def new_route_bob(org_id_bob):
    return Route.objects.create(owner_id=org_id_bob)


class TestRouteCreation:
    url = reverse('route-list', kwargs={'version': 'v1'})

    def test_requires_authentication(self, api_client):
        response = api_client.post(self.url)
        AssertionHelper.HTTP_403(response)

    def test_no_attributes(self, client_alice, user_alice):
        response = client_alice.post(self.url)
        AssertionHelper.HTTP_201(response, entity_refs=AssertionHelper.EntityRef(
            resource='Route',
        ))

    def test_owner_is_caller_org(self, client_alice, org_id_alice):
        response = client_alice.post(self.url)
        AssertionHelper.HTTP_201(response, entity_refs=AssertionHelper.EntityRef(
            resource='Route',
            attributes={'owner_id': org_id_alice}
        ))

    def test_owner_is_caller_no_org(self, client_lionel, user_lionel_id):
        response = client_lionel.post(self.url)
        AssertionHelper.HTTP_201(response, entity_refs=AssertionHelper.EntityRef(
            resource='Route',
            attributes={'owner_id': user_lionel_id}
        ))

    def test_with_attributes(self, client_alice, route_attributes):
        response = client_alice.post(self.url, route_attributes)
        AssertionHelper.HTTP_201(
            response,
            entity_refs=AssertionHelper.EntityRef(
                resource='Route',
                attributes={
                    'name': route_attributes['name'],
                    'driver_id': route_attributes['driver_id'],
                },
            ),
        )

    def test_with_device_not_authorized_fails(self, client_alice, route_attributes, device):
        route_attributes['device_id'] = device.id

        with mock.patch('apps.shipments.models.Device.get_or_create_with_permission') as mock_device:
            mock_error = 'mock unauthorized error'
            mock_device.side_effect = ValidationError(mock_error)

            response = client_alice.post(self.url, route_attributes)
            AssertionHelper.HTTP_400(response, error=mock_error)

    def test_with_unassociated_device(self, client_alice, route_attributes, device):
        route_attributes['device_id'] = device.id

        with mock.patch('apps.shipments.models.Device.get_or_create_with_permission') as mock_device:
            mock_device.return_value = device

            response = client_alice.post(self.url, route_attributes)
            AssertionHelper.HTTP_201(
                response,
                entity_refs=AssertionHelper.EntityRef(
                    resource='Route',
                    attributes={
                        'name': route_attributes['name'],
                        'driver_id': route_attributes['driver_id'],
                    },
                    relationships={
                        'device': AssertionHelper.EntityRef(
                            resource='Device',
                            pk=route_attributes['device_id']
                        ),
                    }
                ),
                included=AssertionHelper.EntityRef(
                    resource='Device',
                    pk=route_attributes['device_id']
                ),
            )

    def test_with_device_blocked_on_shipment_fails(self, client_alice, route_attributes, shipment_alice_with_device):
        route_attributes['device_id'] = shipment_alice_with_device.device.id

        shipment_alice_with_device.pick_up()
        shipment_alice_with_device.save()

        with mock.patch('apps.shipments.models.Device.get_or_create_with_permission') as mock_device:
            mock_device.return_value = shipment_alice_with_device.device

            response = client_alice.post(self.url, route_attributes)
            AssertionHelper.HTTP_400(response, error='Device is already assigned to a Shipment in progress')

    def test_with_device_available_on_shipment(self, client_alice, route_attributes, shipment_alice_with_device):
        route_attributes['device_id'] = shipment_alice_with_device.device.id

        with mock.patch('apps.shipments.models.Device.get_or_create_with_permission') as mock_device:
            mock_device.return_value = shipment_alice_with_device.device

            response = client_alice.post(self.url, route_attributes)
            AssertionHelper.HTTP_201(
                response,
                entity_refs=AssertionHelper.EntityRef(
                    resource='Route',
                    attributes={
                        'name': route_attributes['name'],
                        'driver_id': route_attributes['driver_id'],
                    },
                    relationships={
                        'device': AssertionHelper.EntityRef(
                            resource='Device',
                            pk=route_attributes['device_id']
                        ),
                    }
                ),
                included=AssertionHelper.EntityRef(
                    resource='Device',
                    pk=route_attributes['device_id']
                ),
            )

    def test_with_device_blocked_on_route_fails(self, client_alice, route_attributes, new_route_with_device, shipment):
        route_attributes['device_id'] = new_route_with_device.device.id

        new_route_with_device.routeleg_set.create(shipment=shipment, sequence=1)
        shipment.pick_up()
        shipment.save()

        with mock.patch('apps.shipments.models.Device.get_or_create_with_permission') as mock_device:
            mock_device.return_value = new_route_with_device.device
            response = client_alice.post(self.url, route_attributes)
            AssertionHelper.HTTP_400(response, error='Device is already assigned to a Route in progress')

    def test_with_device_available_on_route(self, client_alice, route_attributes, new_route_with_device):
        route_attributes['device_id'] = new_route_with_device.device.id

        with mock.patch('apps.shipments.models.Device.get_or_create_with_permission') as mock_device:
            mock_device.return_value = new_route_with_device.device
            response = client_alice.post(self.url, route_attributes)
            AssertionHelper.HTTP_201(
                response,
                entity_refs=AssertionHelper.EntityRef(
                    resource='Route',
                    attributes={
                        'name': route_attributes['name'],
                        'driver_id': route_attributes['driver_id'],
                    },
                    relationships={
                        'device': AssertionHelper.EntityRef(
                            resource='Device',
                            pk=route_attributes['device_id']
                        ),
                    }
                ),
                included=AssertionHelper.EntityRef(
                    resource='Device',
                    pk=route_attributes['device_id']
                ),
            )


class TestRouteUpdate:

    @fixture(autouse=True)
    def setup_url(self, new_route, new_route_with_device):
        self.url_random = reverse('route-detail', kwargs={'version': 'v1', 'pk': random_id()})
        self.url_route = reverse('route-detail', kwargs={'version': 'v1', 'pk': new_route.id})
        self.url_route_device = reverse('route-detail', kwargs={'version': 'v1', 'pk': new_route_with_device.id})

    def test_requires_authentication(self, api_client):
        response = api_client.patch(self.url_route)
        AssertionHelper.HTTP_403(response)

    def test_invalid_route(self, client_alice):
        response = client_alice.patch(self.url_random)
        AssertionHelper.HTTP_404(response)

    def test_creator_update(self, client_alice, route_attributes, new_route):
        response = client_alice.patch(self.url_route, data=route_attributes)
        AssertionHelper.HTTP_200(
            response,
            entity_refs=AssertionHelper.EntityRef(
                resource='Route',
                pk=new_route.id,
                attributes={
                    'name': route_attributes['name'],
                    'driver_id': route_attributes['driver_id'],
                }
            )
        )

    def test_org_member_update(self, client_carol, route_attributes, new_route, org_id_alice):
        response = client_carol.patch(self.url_route, data=route_attributes)
        AssertionHelper.HTTP_200(
            response,
            entity_refs=AssertionHelper.EntityRef(
                resource='Route',
                pk=new_route.id,
                attributes={
                    'name': route_attributes['name'],
                    'driver_id': route_attributes['driver_id'],
                    'owner_id': org_id_alice,
                }
            )
        )

    def test_outside_org_fails(self, client_bob, route_attributes):
        response = client_bob.patch(self.url_route, data=route_attributes)
        AssertionHelper.HTTP_404(response)

    def test_add_unassociated_device(self, client_alice, route_attributes, new_route, device):
        route_attributes['device_id'] = device.id

        with mock.patch('apps.shipments.models.Device.get_or_create_with_permission') as mock_device:
            mock_device.return_value = device

            response = client_alice.patch(self.url_route, route_attributes)
            AssertionHelper.HTTP_200(
                response,
                entity_refs=AssertionHelper.EntityRef(
                    resource='Route',
                    attributes={
                        'name': route_attributes['name'],
                        'driver_id': route_attributes['driver_id'],
                    },
                    relationships={
                        'device': AssertionHelper.EntityRef(
                            resource='Device',
                            pk=route_attributes['device_id']
                        ),
                    }
                ),
                included=AssertionHelper.EntityRef(
                    resource='Device',
                    pk=route_attributes['device_id']
                ),
            )

    def test_with_device_blocked_on_shipment_fails(self, client_alice, route_attributes, shipment_alice_with_device):
        route_attributes['device_id'] = shipment_alice_with_device.device.id

        shipment_alice_with_device.pick_up()
        shipment_alice_with_device.save()

        with mock.patch('apps.shipments.models.Device.get_or_create_with_permission') as mock_device:
            mock_device.return_value = shipment_alice_with_device.device

            response = client_alice.patch(self.url_route, route_attributes)
            AssertionHelper.HTTP_400(response, error='Device is already assigned to a Shipment in progress')

    def test_with_device_available_on_shipment(self, client_alice, route_attributes, shipment_alice_with_device):
        route_attributes['device_id'] = shipment_alice_with_device.device.id

        with mock.patch('apps.shipments.models.Device.get_or_create_with_permission') as mock_device:
            mock_device.return_value = shipment_alice_with_device.device

            response = client_alice.patch(self.url_route, route_attributes)
            AssertionHelper.HTTP_200(
                response,
                entity_refs=AssertionHelper.EntityRef(
                    resource='Route',
                    attributes={
                        'name': route_attributes['name'],
                        'driver_id': route_attributes['driver_id'],
                    },
                    relationships={
                        'device': AssertionHelper.EntityRef(
                            resource='Device',
                            pk=route_attributes['device_id']
                        ),
                    }
                ),
                included=AssertionHelper.EntityRef(
                    resource='Device',
                    pk=route_attributes['device_id']
                ),
            )

    def test_with_device_blocked_on_route_fails(self, client_alice, route_attributes, new_route_with_device, shipment):
        route_attributes['device_id'] = new_route_with_device.device.id

        new_route_with_device.routeleg_set.create(shipment=shipment, sequence=1)
        shipment.pick_up()
        shipment.save()

        with mock.patch('apps.shipments.models.Device.get_or_create_with_permission') as mock_device:
            mock_device.return_value = new_route_with_device.device
            response = client_alice.patch(self.url_route, route_attributes)
            AssertionHelper.HTTP_400(response, error='Device is already assigned to a Route in progress')

    def test_with_device_available_on_route(self, client_alice, route_attributes, new_route_with_device):
        route_attributes['device_id'] = new_route_with_device.device.id

        with mock.patch('apps.shipments.models.Device.get_or_create_with_permission') as mock_device:
            mock_device.return_value = new_route_with_device.device
            response = client_alice.patch(self.url_route, route_attributes)
            AssertionHelper.HTTP_200(
                response,
                entity_refs=AssertionHelper.EntityRef(
                    resource='Route',
                    attributes={
                        'name': route_attributes['name'],
                        'driver_id': route_attributes['driver_id'],
                    },
                    relationships={
                        'device': AssertionHelper.EntityRef(
                            resource='Device',
                            pk=route_attributes['device_id']
                        ),
                    }
                ),
                included=AssertionHelper.EntityRef(
                    resource='Device',
                    pk=route_attributes['device_id']
                ),
            )

    def test_remove_device_no_shipments(self, client_alice, route_attributes, new_route_with_device):
        route_attributes['device_id'] = None

        response = client_alice.patch(self.url_route_device, data=route_attributes)
        AssertionHelper.HTTP_200(
            response,
            entity_refs=AssertionHelper.EntityRef(
                resource='Route',
                pk=new_route_with_device.id,
                attributes={
                    'name': route_attributes['name'],
                    'driver_id': route_attributes['driver_id'],
                }
            )
        )

        route = Route.objects.get(pk=new_route_with_device.id)
        assert not route.device

    def test_remove_device_in_progress_fails(self, client_alice, route_attributes, new_route_with_device, shipment):
        route_attributes['device_id'] = None

        new_route_with_device.routeleg_set.create(shipment=shipment, sequence=1)
        shipment.pick_up()
        shipment.save()

        response = client_alice.patch(self.url_route_device, data=route_attributes)
        print(response.json())
        AssertionHelper.HTTP_400(response, error='Cannot remove device from Route in progress')

        route = Route.objects.get(pk=new_route_with_device.id)
        assert route.device

    def test_remove_device_not_in_progress(self, client_alice, route_attributes, new_route_with_device, shipment):
        route_attributes['device_id'] = None

        new_route_with_device.routeleg_set.create(shipment=shipment, sequence=1)

        response = client_alice.patch(self.url_route_device, data=route_attributes)
        AssertionHelper.HTTP_200(
            response,
            entity_refs=AssertionHelper.EntityRef(
                resource='Route',
                pk=new_route_with_device.id,
                attributes={
                    'name': route_attributes['name'],
                    'driver_id': route_attributes['driver_id'],
                }
            )
        )

        route = Route.objects.get(pk=new_route_with_device.id)
        assert not route.device


class TestRouteDelete:

    @fixture(autouse=True)
    def setup_url(self, new_route, new_route_with_device):
        self.url_random = reverse('route-detail', kwargs={'version': 'v1', 'pk': random_id()})
        self.url_route = reverse('route-detail', kwargs={'version': 'v1', 'pk': new_route.id})
        self.url_route_device = reverse('route-detail', kwargs={'version': 'v1', 'pk': new_route_with_device.id})

    def test_requires_authentication(self, api_client):
        response = api_client.delete(self.url_route)
        AssertionHelper.HTTP_403(response)

    def test_invalid_route(self, client_alice):
        response = client_alice.delete(self.url_random)
        AssertionHelper.HTTP_404(response)

    def test_creator_can_delete(self, client_alice, new_route):
        response = client_alice.delete(self.url_route)
        AssertionHelper.HTTP_204(response)
        route = Route.objects.filter(pk=new_route.id).first()
        assert not route

    def test_org_member_can_delete(self, client_carol, new_route):
        response = client_carol.delete(self.url_route)
        AssertionHelper.HTTP_204(response)
        route = Route.objects.filter(pk=new_route.id).first()
        assert not route

    def test_outside_org_fails(self, client_bob, new_route):
        response = client_bob.delete(self.url_route)
        AssertionHelper.HTTP_404(response)
        route = Route.objects.filter(pk=new_route.id).first()
        assert route


class TestRouteRetrieve:

    @fixture(autouse=True)
    def setup_url(self, new_route):
        self.url_random = reverse('route-detail', kwargs={'version': 'v1', 'pk': random_id()})
        self.url_route = reverse('route-detail', kwargs={'version': 'v1', 'pk': new_route.id})

    def test_requires_authentication(self, api_client):
        response = api_client.get(self.url_route)
        AssertionHelper.HTTP_403(response)

    def test_invalid_route(self, client_alice):
        response = client_alice.get(self.url_random)
        AssertionHelper.HTTP_404(response)

    def test_creator_get(self, client_alice, new_route):
        response = client_alice.get(self.url_route)
        AssertionHelper.HTTP_200(
            response,
            entity_refs=AssertionHelper.EntityRef(
                resource='Route',
                pk=new_route.id,
                attributes={
                    'name': new_route.name,
                    'driver_id': new_route.driver_id,
                }
            )
        )

    def test_org_member_get(self, client_carol, new_route, org_id_alice):
        response = client_carol.get(self.url_route)
        AssertionHelper.HTTP_200(
            response,
            entity_refs=AssertionHelper.EntityRef(
                resource='Route',
                pk=new_route.id,
                attributes={
                    'name': new_route.name,
                    'driver_id': new_route.driver_id,
                    'owner_id': org_id_alice,
                }
            )
        )

    def test_outside_org_fails(self, client_bob, route_attributes):
        response = client_bob.get(self.url_route, data=route_attributes)
        AssertionHelper.HTTP_404(response)

    def test_includes_legs(self, client_alice, new_route, shipment_alice_with_device, shipment):
        leg1 = new_route.routeleg_set.create(shipment=shipment, sequence=1)
        leg2 = new_route.routeleg_set.create(shipment=shipment_alice_with_device, sequence=2)

        leg1_entity = AssertionHelper.EntityRef(resource='RouteLeg', pk=leg1.pk,
                                                attributes={'shipment_id': shipment.pk})
        leg2_entity = AssertionHelper.EntityRef(resource='RouteLeg', pk=leg2.pk,
                                                attributes={'shipment_id': shipment_alice_with_device.pk})

        response = client_alice.get(self.url_route)
        AssertionHelper.HTTP_200(
            response,
            entity_refs=AssertionHelper.EntityRef(
                resource='Route',
                pk=new_route.id,
                attributes={
                    'name': new_route.name,
                    'driver_id': new_route.driver_id,
                },
                relationships={
                    'legs': [leg1_entity, leg2_entity]
                },
            ),
            included=[leg1_entity, leg2_entity]
        )


class TestRouteAddLeg:

    @fixture
    def shipment_on_new_route(self, shipment, new_route):
        new_route.routeleg_set.create(shipment=shipment, sequence=1)
        return shipment

    @fixture
    def leg_attributes(self):
        return {
            'shipment_id': random_id(),
        }

    @fixture(autouse=True)
    def setup_url(self, new_route, new_route_with_device, new_route_bob):
        self.url_random = reverse('route-legs-list', kwargs={'version': 'v1', 'route_pk': random_id()})
        self.url_route = reverse('route-legs-list', kwargs={'version': 'v1', 'route_pk': new_route.id})
        self.url_route_device = reverse('route-legs-list',
                                        kwargs={'version': 'v1', 'route_pk': new_route_with_device.id})
        self.url_route_bob = reverse('route-legs-list', kwargs={'version': 'v1', 'route_pk': new_route_bob.id})

    def test_requires_authentication(self, api_client):
        response = api_client.post(self.url_route)
        AssertionHelper.HTTP_403(response)

    def test_invalid_route(self, client_alice, leg_attributes):
        response = client_alice.post(self.url_random, data=leg_attributes)
        AssertionHelper.HTTP_404(response, error='Route matching query does not exist')

    def test_invalid_shipment(self, client_alice, leg_attributes):
        response = client_alice.post(self.url_route, data=leg_attributes)
        AssertionHelper.HTTP_400(response, error='Shipment does not exist')

    def test_route_in_progress_fails(self, client_alice, leg_attributes, shipment_on_new_route, shipment_alice):
        shipment_on_new_route.pick_up()
        shipment_on_new_route.save()

        leg_attributes['shipment_id'] = shipment_alice.pk

        response = client_alice.post(self.url_route, data=leg_attributes)
        AssertionHelper.HTTP_400(response, error='Cannot add shipment to route after transit has begun')

    def test_route_complete_fails(self, client_alice, leg_attributes, shipment_on_new_route, shipment_alice):
        shipment_on_new_route.pick_up()
        shipment_on_new_route.save()
        shipment_on_new_route.arrival()
        shipment_on_new_route.save()
        shipment_on_new_route.drop_off()
        shipment_on_new_route.save()

        leg_attributes['shipment_id'] = shipment_alice.pk

        response = client_alice.post(self.url_route, data=leg_attributes)
        AssertionHelper.HTTP_400(response, error='Cannot add shipment to route after transit has begun')

    def test_shipment_in_progress_fails(self, client_alice, leg_attributes, shipment):
        shipment.pick_up()
        shipment.save()

        leg_attributes['shipment_id'] = shipment.pk

        response = client_alice.post(self.url_route, data=leg_attributes)
        AssertionHelper.HTTP_400(response, error='Shipment already picked up, cannot add to route')

    def test_shipment_complete_fails(self, client_alice, leg_attributes, shipment):
        shipment.pick_up()
        shipment.save()
        shipment.arrival()
        shipment.save()
        shipment.drop_off()
        shipment.save()

        leg_attributes['shipment_id'] = shipment.pk

        response = client_alice.post(self.url_route, data=leg_attributes)
        AssertionHelper.HTTP_400(response, error='Shipment already picked up, cannot add to route')

    def test_shipment_with_device_fails(self, client_alice, leg_attributes, shipment_alice_with_device):
        leg_attributes['shipment_id'] = shipment_alice_with_device.pk

        response = client_alice.post(self.url_route, data=leg_attributes)
        AssertionHelper.HTTP_400(response, error='Shipment has device associated, cannot add to route')

    def test_own_shipment(self, client_alice, leg_attributes, shipment):
        leg_attributes['shipment_id'] = shipment.pk

        response = client_alice.post(self.url_route, data=leg_attributes)
        AssertionHelper.HTTP_201(
            response,
            entity_refs=AssertionHelper.EntityRef(
                resource='RouteLeg',
                attributes={
                    'shipment_id': shipment.pk,
                },
            )
        )

    def test_org_shipment(self, client_alice, leg_attributes, second_shipment):
        leg_attributes['shipment_id'] = second_shipment.pk

        response = client_alice.post(self.url_route, data=leg_attributes)
        AssertionHelper.HTTP_201(
            response,
            entity_refs=AssertionHelper.EntityRef(
                resource='RouteLeg',
                attributes={
                    'shipment_id': second_shipment.pk,
                },
            )
        )

    def test_other_org_shipment_fails(self, client_bob, leg_attributes, shipment, mocked_not_shipper,
                                      mocked_not_carrier, mocked_not_moderator):
        leg_attributes['shipment_id'] = shipment.pk

        response = client_bob.post(self.url_route_bob, data=leg_attributes)
        AssertionHelper.HTTP_400(response, error='Shipment does not exist')


class TestRouteRemoveLeg:

    @fixture(autouse=True)
    def setup_url(self, new_route, new_route_with_device, new_route_bob, shipment, org2_shipment):
        leg = new_route.routeleg_set.create(shipment=shipment, sequence=1)
        leg_bob = new_route_bob.routeleg_set.create(shipment=org2_shipment, sequence=1)
        self.url_random_route = reverse('route-legs-detail',
                                        kwargs={'version': 'v1', 'route_pk': random_id(), 'pk': leg.pk})
        self.url_route = reverse('route-legs-detail', kwargs={'version': 'v1', 'route_pk': new_route.id, 'pk': leg.pk})
        self.url_random_leg = reverse('route-legs-detail',
                                      kwargs={'version': 'v1', 'route_pk': new_route_with_device.id, 'pk': random_id()})
        self.url_route_bob = reverse('route-legs-detail',
                                     kwargs={'version': 'v1', 'route_pk': new_route_bob.id, 'pk': leg_bob.pk})

    def test_requires_authentication(self, api_client):
        response = api_client.delete(self.url_route)
        AssertionHelper.HTTP_403(response)

    def test_invalid_route(self, client_alice):
        response = client_alice.delete(self.url_random_route)
        AssertionHelper.HTTP_404(response, error='Route matching query does not exist')

    def test_invalid_leg(self, client_alice):
        response = client_alice.delete(self.url_random_leg)
        AssertionHelper.HTTP_404(response)

    def test_other_org(self, client_alice):
        response = client_alice.delete(self.url_route_bob)
        AssertionHelper.HTTP_404(response, error='Route matching query does not exist')

    def test_not_yet_started(self, client_alice):
        response = client_alice.delete(self.url_route)
        AssertionHelper.HTTP_204(response)

    def test_route_in_progress_fails(self, client_alice, shipment):
        shipment.pick_up()
        shipment.save()

        response = client_alice.delete(self.url_route)
        AssertionHelper.HTTP_400(response, error='Cannot remove shipment from route after transit has begun')

    def test_route_complete_fails(self, client_alice, shipment):
        shipment.pick_up()
        shipment.save()
        shipment.arrival()
        shipment.save()
        shipment.drop_off()
        shipment.save()

        response = client_alice.delete(self.url_route)
        AssertionHelper.HTTP_400(response, error='Cannot remove shipment from route after transit has begun')
