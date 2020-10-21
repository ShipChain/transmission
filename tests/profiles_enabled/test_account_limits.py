from django.urls import reverse
from pytest import fixture
from shipchain_common.test_utils import AssertionHelper


class TestLimits:
    @fixture(autouse=True)
    def setup_urls(self, shipment_alice, mock_successful_wallet_owner_calls):
        self.list_url = reverse('shipment-list', kwargs={'version': 'v1'})
        self.document_url = reverse('shipment-documents-list', kwargs={'version': 'v1', 'shipment_pk': shipment_alice.id})

    def test_org_shipment_active_limit(self, client_alice_limited, profiles_ids):
        # One shipment already exists (shipment_alice), second shipment should trigger 402
        response = client_alice_limited.post(self.list_url, profiles_ids)
        AssertionHelper.HTTP_402(response)

    def test_org_shipment_document_limit(self, client_alice_limited, profiles_ids):
        document_data = {
            'name': 'Test BOL',
            'file_type': 'PDF',
            'document_type': 'AIR_WAYBILL'
        }
        response = client_alice_limited.post(self.document_url, document_data)
        AssertionHelper.HTTP_201(response)
        response = client_alice_limited.post(self.document_url, document_data)
        AssertionHelper.HTTP_402(response)
