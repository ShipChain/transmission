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

import glob
from unittest import mock
import copy
import os
import requests
import pyexcel

from django.conf import settings
from rest_framework import status
from rest_framework.reverse import reverse
from rest_framework.test import APITestCase, APIClient
from rest_framework_json_api.serializers import ValidationError

from apps.authentication import passive_credentials_auth
from apps.imports.models import ShipmentImport

from tests.utils import get_jwt, random_timestamp


OWNER_ID = '5e8f1d76-162d-4f21-9b71-2ca97306ef7c'
CARRIER_WALLET_ID = '3716ff65-3d03-4b65-9fd5-43d15380cff9'
SHIPPER_WALLET_ID = '48381c16-432b-493f-9f8b-54e88a84ec0a'
STORAGE_CRED_ID = '77b72202-5bcd-49f4-9860-bc4ec4fee07b'


class ShipmentImportsViewSetAPITests(APITestCase):

    def setUp(self):
        self.client = APIClient()

        self.user_1 = passive_credentials_auth(get_jwt(username='test_user1@shipchain.io', sub=OWNER_ID))
        self.user_2 = passive_credentials_auth(get_jwt(username='test_user2@shipchain.io'))

        self.s3 = settings.S3_RESOURCE

        for bucket in self.s3.buckets.all():
            for key in bucket.objects.all():
                key.delete()
            bucket.delete()

        try:
            self.s3.create_bucket(Bucket=settings.SHIPMENT_IMPORTS_BUCKET)
        except Exception as exc:
            pass

    def tearDown(self):
        files = glob.glob('./tests/tmp/*.*')
        for f in files:
            os.remove(f)

    def set_user(self, user, token=None):
        self.client.force_authenticate(user=user, token=token)

    def make_shipment_file(self, file_path, data=None):
        default_data = [
            {
                'shipment_name': 'Test shipment 1',
                'creation-date': random_timestamp()
            },
            {
                'shipment_name': 'Test shipment 2',
                'creation-date': random_timestamp()
            }
        ]
        data_to_save = data if data else default_data
        pyexcel.save_as(records=data_to_save, dest_file_name=file_path)

    def s3_object_exists(self, key):
        try:
            self.s3.Object(settings.SHIPMENT_IMPORTS_BUCKET, key).get()
        except Exception:
            return False
        return True

    def test_shipment_imports(self):

        url = reverse('import-shipments-list', kwargs={'version': 'v1'})

        csv_path = './tests/tmp/test.csv'
        xls_path = './tests/tmp/test.xls'
        xlsx_path = './tests/tmp/test.xlsx'

        self.make_shipment_file(csv_path)
        self.make_shipment_file(xls_path)
        self.make_shipment_file(xlsx_path)

        csv_file_data = {
            'name': 'Test csv file',
            'description': 'Auto generated file for test purposes',
            'file_type': 'csv',
            'storage_credentials_id': STORAGE_CRED_ID,
            'shipper_wallet_id': SHIPPER_WALLET_ID,
            'carrier_wallet_id': CARRIER_WALLET_ID
        }

        xls_file_data = copy.deepcopy(csv_file_data)
        xls_file_data['name'] = 'Test xls file'
        xls_file_data['file_type'] = 'Xls'
        xls_file_data['upload_status'] = 'complete'

        xlsx_file_data = copy.deepcopy(csv_file_data)
        xlsx_file_data['name'] = 'Test xlsx file'
        xlsx_file_data['file_type'] = '2'
        xlsx_file_data['processing_status'] = 'failed'

        # Unauthenticated user should fail
        response = self.client.post(url, csv_file_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        self.set_user(self.user_1)

        with mock.patch('apps.imports.serializers.ShipmentImportCreateSerializer.validate_shipper_wallet_id') as mock_wallet_validation, \
                mock.patch('apps.imports.serializers.ShipmentImportCreateSerializer.validate_storage_credentials_id') as mock_storage_validation:

            mock_wallet_validation.return_value = SHIPPER_WALLET_ID
            mock_storage_validation.return_value = STORAGE_CRED_ID

            # --------------------- Upload csv file --------------------#
            # Authenticated request should succeed
            response = self.client.post(url, csv_file_data, format='json')
            self.assertEqual(response.status_code, status.HTTP_201_CREATED)
            data = response.json()['data']
            self.assertEqual(data['attributes']['upload_status'], 'PENDING')
            csv_obj = ShipmentImport.objects.get(id=data['id'])
            fields = data['meta']['presigned_s3']['fields']

            # csv file upload
            put_url = data['meta']['presigned_s3']['url']
            with open(csv_path, 'rb') as csv:
                res = requests.post(put_url, data=fields, files={'file': csv})

            self.assertEqual(res.status_code, status.HTTP_204_NO_CONTENT)
            self.assertTrue(self.s3_object_exists(csv_obj.s3_key))

            # --------------------- Upload xls file --------------------#
            response = self.client.post(url, xls_file_data, format='json')
            self.assertEqual(response.status_code, status.HTTP_201_CREATED)
            data = response.json()['data']
            # upload_status field is not configurable at creation
            self.assertEqual(data['attributes']['upload_status'], 'PENDING')
            self.assertEqual(data['attributes']['processing_status'], 'PENDING')
            # Wallets and storage should be present in response
            self.assertEqual(data['attributes'].get('storage_credentials_id'), STORAGE_CRED_ID)
            self.assertEqual(data['attributes'].get('shipper_wallet_id'), SHIPPER_WALLET_ID)
            self.assertEqual(data['attributes'].get('carrier_wallet_id'), CARRIER_WALLET_ID)
            xls_obj = ShipmentImport.objects.get(id=data['id'])
            fields = data['meta']['presigned_s3']['fields']

            # xls file upload
            put_url = data['meta']['presigned_s3']['url']
            with open(xls_path, 'rb') as xls:
                res = requests.post(put_url, data=fields, files={'file': xls})

            self.assertEqual(res.status_code, status.HTTP_204_NO_CONTENT)
            self.assertTrue(self.s3_object_exists(xls_obj.s3_key))

            # --------------------- Upload xlsx file --------------------#
            response = self.client.post(url, xlsx_file_data, format='json')
            self.assertEqual(response.status_code, status.HTTP_201_CREATED)
            data = response.json()['data']
            self.assertEqual(data['attributes']['upload_status'], 'PENDING')
            # processing_status field is not configurable at creation
            self.assertEqual(data['attributes']['processing_status'], 'PENDING')
            xlsx_obj = ShipmentImport.objects.get(id=data['id'])
            fields = data['meta']['presigned_s3']['fields']

            # xlsx file upload
            put_url = data['meta']['presigned_s3']['url']
            with open(xlsx_path, 'rb') as xlsx:
                res = requests.post(put_url, data=fields, files={'file': xlsx})

            self.assertEqual(res.status_code, status.HTTP_204_NO_CONTENT)
            self.assertTrue(self.s3_object_exists(xlsx_obj.s3_key))

            # -------------------- test patch object -------------------#
            patch_csv_data = {
                'name': 'Can update name',
                'file_type': 'XLS',     # Cannot be modified
                'owner_id': 'new_owner_id',     # Cannot be modified
                'masquerade_id': 'new_masquerade_id',     # Cannot be modified
                "upload_status": "Complete",
                "processing_status": "Complete",
                "report": {
                    "success": 15,
                    "failed": 0
                }
            }
            csv_patch_url = f'{url}/{csv_obj.id}/'
            response = self.client.patch(csv_patch_url, data=patch_csv_data, format='json')
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            data = response.json()['data']
            # The file_type cannot change on patch
            self.assertEqual(data['attributes']['file_type'], 'CSV')
            self.assertEqual(data['attributes']['report'], patch_csv_data['report'])
            self.assertEqual(data['attributes']['processing_status'], 'COMPLETE')
            # Wallets and storage, should be present in the response object and are non modifiable
            self.assertEqual(data['attributes'].get('storage_credentials_id'), STORAGE_CRED_ID)
            self.assertEqual(data['attributes'].get('shipper_wallet_id'), SHIPPER_WALLET_ID)
            self.assertEqual(data['attributes'].get('carrier_wallet_id'), CARRIER_WALLET_ID)
            # owner_id and masquerade_id shouldn't be present in the response object
            self.assertIsNone(data['attributes'].get('owner_id'))
            self.assertIsNone(data['attributes'].get('masquerade_id'))

            # wallet and storage are non modifiable fields
            new_wallet_id = 'Wallet_is_Non_Modifiable'
            mock_wallet_validation.reset_mock()
            mock_wallet_validation.return_value = new_wallet_id

            patch_csv_data['shipper_wallet_id'] = new_wallet_id

            response = self.client.patch(csv_patch_url, data=patch_csv_data, format='json')
            self.assertEqual(mock_wallet_validation.call_count, 0)
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            data = response.json()['data']
            # The shipper_wallet_id attribute cannot be patched
            self.assertEqual(data['attributes']['shipper_wallet_id'], SHIPPER_WALLET_ID)
            csv_obj.refresh_from_db()
            self.assertEqual(csv_obj.shipper_wallet_id, SHIPPER_WALLET_ID)

            # ------------------ permissions test -----------------------#
            self.set_user(self.user_2)

            # user_2 can create an xls file object
            response = self.client.post(url, xlsx_file_data, format='json')
            self.assertEqual(response.status_code, status.HTTP_201_CREATED)

            # user_2 cannot access a document object not owned
            user_1_xlsx_url = f'{url}/{xlsx_obj.id}/'
            response = self.client.get(user_1_xlsx_url)
            self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

            # user_2 cannot modify a document object not owned
            user_1_xlsx_url = f'{url}/{xlsx_obj.id}/'
            response = self.client.patch(user_1_xlsx_url, data=patch_csv_data)
            self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

            # user_2 can list only document owned
            response = self.client.get(url)
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            data = response.json()['data']
            self.assertEqual(len(data), 1)
            user_2_csv_document = ShipmentImport.objects.get(id=data[0]['id'])
            self.assertEqual(user_2_csv_document.masquerade_id, self.user_2.id)

            mock_wallet_validation.reset_mock()

            # Trying to upload a document without a shipper wallet should fail
            csv_file_data_without_shipper_wallet = copy.deepcopy(csv_file_data)
            csv_file_data_without_shipper_wallet.pop('shipper_wallet_id')

            response = self.client.post(url, csv_file_data_without_shipper_wallet, format='json')
            self.assertEqual(mock_wallet_validation.call_count, 0)
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

            # Trying to upload a document with a wallet / storage not owned by the requester should fail
            error_message = 'User does not have access to this wallet in ShipChain Profiles'
            mock_wallet_validation.side_effect = ValidationError(error_message)
            mock_wallet_validation.return_value = None

            csv_file_data_with_invalid_shipper_wallet = copy.deepcopy(csv_file_data)
            csv_file_data_with_invalid_shipper_wallet['shipper_wallet_id'] = 'Non_Accessible_Wallet'

            response = self.client.post(url, csv_file_data_with_invalid_shipper_wallet, format='json')
            self.assertEqual(mock_wallet_validation.call_count, 1)
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
            data = response.json()['errors'][0]
            self.assertEqual(data['detail'], error_message)


