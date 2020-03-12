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

from rest_framework import status
from rest_framework.reverse import reverse
from rest_framework.test import APITestCase, APIClient


USER_ID = 'profiles-disabled-user-id'
OWNER_ID = 'profiles-disabled-owner-id'
CARRIER_WALLET_ID = '3716ff65-3d03-4b65-9fd5-43d15380cff9'
SHIPPER_WALLET_ID = '48381c16-432b-493f-9f8b-54e88a84ec0a'
STORAGE_CRED_ID = '77b72202-5bcd-49f4-9860-bc4ec4fee07b'


class ShipmentImportsViewSetAPITests(APITestCase):

    def setUp(self):
        self.client = APIClient()

    def test_shipment_imports(self):

        url = reverse('import-shipments-list', kwargs={'version': 'v1'})

        csv_file_data = {
            'name': 'Test csv file',
            'description': 'Auto generated file for test purposes',
            'file_type': 'csv',
            'storage_credentials_id': STORAGE_CRED_ID,
            'shipper_wallet_id': SHIPPER_WALLET_ID,
            'carrier_wallet_id': CARRIER_WALLET_ID,
            'masquerade_id': USER_ID,
            'owner_id': OWNER_ID,
        }

        response = self.client.post(url, csv_file_data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        data = response.json()['data']
        self.assertEqual(data['attributes']['upload_status'], 'PENDING')
        self.assertTrue(isinstance(data['meta']['presigned_s3']['fields'], dict))

        # Ensure the shipment import comes
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()['data']
        self.assertEqual(len(data), 1)
