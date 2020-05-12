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