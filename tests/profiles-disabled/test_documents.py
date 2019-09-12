"""
Copyright 2019 ShipChain, Inc.

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

from unittest import mock

from django.db.models import signals
from rest_framework import status
from rest_framework.reverse import reverse
from rest_framework.test import APITestCase, APIClient

from apps.documents.models import Document
from apps.rpc_client import requests as rpc_requests
from apps.shipments.models import Shipment
from apps.shipments.signals import shipment_post_save
from tests.utils import mocked_rpc_response

OWNER_ID = '5e8f1d76-162d-4f21-9b71-2ca97306ef7c'
VAULT_ID = 'b715a8ff-9299-4c87-96de-a4b0a4a54509'
CARRIER_WALLET_ID = '3716ff65-3d03-4b65-9fd5-43d15380cff9'
SHIPPER_WALLET_ID = '48381c16-432b-493f-9f8b-54e88a84ec0a'
STORAGE_CRED_ID = '77b72202-5bcd-49f4-9860-bc4ec4fee07b'


class DocumentViewSetAPITests(APITestCase):

    def setUp(self):
        self.client = APIClient()

        # Disable Shipment post save signal
        signals.post_save.disconnect(sender=Shipment, dispatch_uid='shipment_post_save')

        self.shipment = Shipment.objects.create(
            vault_id=VAULT_ID,
            carrier_wallet_id=CARRIER_WALLET_ID,
            shipper_wallet_id=SHIPPER_WALLET_ID,
            storage_credentials_id=STORAGE_CRED_ID,
            owner_id=OWNER_ID
        )

        # Re-enable Shipment post save signal
        signals.post_save.connect(shipment_post_save, sender=Shipment, dispatch_uid='shipment_post_save')

    def test_create_document(self):
        url = reverse('shipment-documents-list', kwargs={'version': 'v1', 'shipment_pk': self.shipment.id})

        file_data = {
            'name': 'Test BOL',
            'owner_id': OWNER_ID,
            'description': 'Auto generated file for test purposes',
            'document_type': 'Bol',
            'file_type': 'Pdf'
        }
        with mock.patch.object(rpc_requests.Session, 'post') as mock_method:
            mock_method.return_value = mocked_rpc_response({
                "success": True
            })

            response = self.client.post(url, file_data, format='json')
            self.assertEqual(response.status_code, status.HTTP_201_CREATED)
            data = response.json()['data']
            self.assertTrue(isinstance(data['meta']['presigned_s3']['fields'], dict))
            document = Document.objects.all()
            self.assertEqual(document.count(), 1)
            self.assertEqual(self.shipment.id, document[0].shipment_id)

            # A request with an invalid shipment_id should fail
            bad_shipment_id = 'non-existing-shipment-in-db'
            bad_shipment_in_url = reverse('shipment-documents-list', kwargs={'version': 'v1', 'shipment_pk': bad_shipment_id})
            response = self.client.post(bad_shipment_in_url, file_data, format='json')
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
