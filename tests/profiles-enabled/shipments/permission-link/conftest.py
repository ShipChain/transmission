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
from datetime import datetime, timedelta
from datetime import timezone

import freezegun
import pytest
from django.urls import reverse
from shipchain_common.test_utils import AssertionHelper

from apps.shipments.models import PermissionLink


@pytest.fixture
def permission_link_shipment_alice(shipment_alice):
    return PermissionLink.objects.create(shipment=shipment_alice, name="Alice Permission Link")


@pytest.fixture
def permission_link_expired(shipment_alice):
    return PermissionLink.objects.create(shipment=shipment_alice, name="Alice Permission Link",
                                         expiration_date=datetime.now(timezone.utc) - timedelta(days=1))


@pytest.fixture
def url_permission_link_detail(permission_link_shipment_alice):
    return reverse('shipment-permissions-detail', kwargs={'version': 'v1', 'pk': permission_link_shipment_alice.id,
                                                          'shipment_pk': permission_link_shipment_alice.shipment.id})


@pytest.fixture
def entity_ref_permission_link(permission_link_shipment_alice, entity_ref_shipment_alice):
    return AssertionHelper.EntityRef(resource='PermissionLink', pk=permission_link_shipment_alice.id,
                                     attributes={'name': permission_link_shipment_alice.name},
                                     relationships=[{'shipment': entity_ref_shipment_alice}])


@pytest.fixture
def entity_ref_permission_link_expired(permission_link_expired, entity_ref_shipment_alice):
    return AssertionHelper.EntityRef(resource='PermissionLink', pk=permission_link_expired.id,
                                     attributes={
                                         'name': permission_link_expired.name,
                                         'expiration_date': permission_link_expired.expiration_date.isoformat().replace('+00:00', 'Z')
                                     },
                                     relationships=[{'shipment': entity_ref_shipment_alice}])


@pytest.fixture
def current_datetime():
    return datetime.now(timezone.utc)


@pytest.fixture(autouse=True)
def frozen_time(current_datetime):
    with freezegun.freeze_time(current_datetime) as current_datetime:
        yield current_datetime
