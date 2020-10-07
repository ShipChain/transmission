"""
Copyright 2020 ShipChain, Inc.

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""
from datetime import datetime
import pytz
from django.urls import reverse
from shipchain_common.test_utils import AssertionHelper


class TestETA:
    def test_eta_read_only(self, client_alice, shipment):
        url = reverse('shipment-detail', kwargs={'version': 'v1', 'pk': shipment.id})
        response = client_alice.patch(url, {'arrival_est': datetime.now(tz=pytz.UTC).isoformat()})
        # Should not be able to update from the frontend
        AssertionHelper.HTTP_202(response,
                                 entity_refs=AssertionHelper.EntityRef(
                                     resource='Shipment',
                                     attributes={'arrival_est': None}
                                 ))

        # Should be able to update on the backend
        shipment.arrival_est = datetime.utcnow().replace(tzinfo=pytz.UTC)
        shipment.save()

        response = client_alice.get(url)
        # Frontend should see backend's new value
        AssertionHelper.HTTP_200(response,
                                 entity_refs=AssertionHelper.EntityRef(
                                     resource='Shipment',
                                     attributes={'arrival_est': shipment.arrival_est.isoformat().replace('+00:00', 'Z')}
                                 ))