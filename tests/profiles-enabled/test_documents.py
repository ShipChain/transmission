import datetime
import glob
import json
from pathlib import Path
from unittest import mock

import os
import requests
from PIL import Image, ImageDraw, ImageFont
from dateutil.parser import parse
from django.conf import settings
from django.db.models import signals
from fpdf import FPDF
from rest_framework import status
from rest_framework.reverse import reverse
from rest_framework.test import APITestCase, APIClient
from shipchain_common.test_utils import create_form_content, get_jwt, mocked_rpc_response

from apps.authentication import passive_credentials_auth
from apps.documents.models import Document, UploadStatus, DocumentType, FileType
from apps.shipments.models import Shipment, LoadShipment
from apps.shipments.signals import shipment_post_save

SHIPMENT_ID = 'Shipment-Custom-Id-{}'
FAKE_ID = '00000000-0000-0000-0000-000000000000'
OWNER_ID = '5e8f1d76-162d-4f21-9b71-2ca97306ef7c'
SHIPPER_ID = '60b2662a-4ec6-4c28-ac1b-2b82ab4b3e03'
CARRIER_ID = 'ff7908cd-6b10-43a7-9fa2-760c4b17dab4'
MODERATOR_ID = '6eeff71e-332e-40e0-8961-f74dab3ff8e0'
ANOTHER_ID = '355d0735-2d63-4054-8577-e675e7fa402b'
VAULT_ID = 'b715a8ff-9299-4c87-96de-a4b0a4a54509'
CARRIER_WALLET_ID = '3716ff65-3d03-4b65-9fd5-43d15380cff9'
SHIPPER_WALLET_ID = '48381c16-432b-493f-9f8b-54e88a84ec0a'
STORAGE_CRED_ID = '77b72202-5bcd-49f4-9860-bc4ec4fee07b'
DEVICE_ID = '332dc6c8-b89e-449e-a802-0bfe760f83ff'
DATE = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
SHIPMENT_ID = SHIPMENT_ID.format(DATE[:10])
VAULT_HASH = '0xe9f28cb025350ef700158eed9a5b617a4f4185b31de06864fd02d67c839df583'


class PdfDocumentViewSetAPITests(APITestCase):

    def setUp(self):
        self.client = APIClient()

        # Disable Shipment post save signal
        signals.post_save.disconnect(sender=Shipment, dispatch_uid='shipment_post_save')

        self.user_1 = passive_credentials_auth(get_jwt(username='user1@shipchain.io', sub=OWNER_ID))

        self.shipment = Shipment.objects.create(
            id=SHIPMENT_ID,
            vault_id=VAULT_ID,
            carrier_wallet_id=CARRIER_WALLET_ID,
            shipper_wallet_id=SHIPPER_WALLET_ID,
            storage_credentials_id=STORAGE_CRED_ID,
            owner_id=OWNER_ID
        )

        # Re-enable Shipment post save signal
        signals.post_save.connect(shipment_post_save, sender=Shipment, dispatch_uid='shipment_post_save')

        s3_resource = settings.S3_RESOURCE

        for bucket in s3_resource.buckets.all():
            for key in bucket.objects.all():
                key.delete()
            bucket.delete()

        try:
            s3_resource.create_bucket(Bucket=settings.DOCUMENT_MANAGEMENT_BUCKET)
        except Exception as exc:
            pass

    def tearDown(self):
        files = glob.glob('./tests/tmp/*.*')
        for f in files:
            os.remove(f)

    def set_user(self, user, token=None):
        self.client.force_authenticate(user=user, token=token)

    def make_pdf_file(self, file_path, message=None):
        default_message = 'Hey There Welcome to Shipchain Transmission.'
        text = message if message else default_message
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font('Arial', 'B', 20)
        pdf.cell(40, 10, text)
        pdf.cell(40, 60, f"{DATE}")
        pdf.output(file_path, 'F')

    def test_sign_to_s3(self):
        url = reverse('shipment-documents-list', kwargs={'version': 'v1', 'shipment_pk': self.shipment.id})

        f_path = './tests/tmp/test_upload.pdf'
        self.make_pdf_file(f_path)

        file_data, content_type = create_form_content({
            'name': 'Test BOL',
            'description': 'Auto generated file for test purposes',
            'document_type': 'Bol',
            'file_type': 'Pdf'
        })

        # Unauthenticated user should fail
        response = self.client.post(url, file_data, content_type=content_type)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        with mock.patch.object(requests.Session, 'post') as mock_method:
            mock_method.return_value = mocked_rpc_response({
                "jsonrpc": "2.0",
                "result": {
                    "success": True,
                },
                "id": 0
            })

            # Authenticated request should succeed
            self.set_user(self.user_1)
            response = self.client.post(url, file_data, content_type=content_type)
            self.assertEqual(response.status_code, status.HTTP_201_CREATED)

            document = Document.objects.all()
            self.assertEqual(document.count(), 1)
            self.assertEqual(self.shipment.id, document[0].shipment_id)

            # Check s3 path integrity in db
            shipment = document[0].shipment
            doc_id = document[0].id
            s3_path = f"s3://{settings.DOCUMENT_MANAGEMENT_BUCKET}/{shipment.storage_credentials_id}/" \
                f"{shipment.shipper_wallet_id}/{shipment.vault_id}/{doc_id}.pdf"
            self.assertEqual(document[0].s3_path, s3_path)

            data = response.json()['data']
            fields = data['meta']['presigned_s3']['fields']

            s3_resource = settings.S3_RESOURCE

            # File upload
            put_url = data['meta']['presigned_s3']['url']
            with open(f_path, 'rb') as pdf:
                res = requests.post(put_url, data=fields, files={'file': pdf})

            self.assertEqual(res.status_code, status.HTTP_204_NO_CONTENT)
            s3_resource.Bucket(settings.DOCUMENT_MANAGEMENT_BUCKET).download_file(fields['key'],
                                                                                  './tests/tmp/downloaded.pdf')

            # We verify the integrity of the uploaded file
            downloaded_file = Path('./tests/tmp/downloaded.pdf')
            self.assertTrue(downloaded_file.exists())

            # Update document object upon upload completion
            url_patch = url + f'/{document[0].id}/'
            file_data, content_type = create_form_content({
                'upload_status': 'COMPLETE',
            })
            response = self.client.patch(url_patch, file_data, content_type=content_type)
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertEqual(document[0].upload_status, UploadStatus.COMPLETE)

            # Tentative to update a fields other than upload_status should fail
            file_data, content_type = create_form_content({
                'document_type': DocumentType.IMAGE,
            })
            response = self.client.patch(url_patch, file_data, content_type=content_type)
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertNotEqual(document[0].document_type, DocumentType.IMAGE)

            # Get a document
            url_get = url + f'/{document[0].id}/'
            response = self.client.get(url_get)
            data = response.json()['data']
            self.assertEqual(response.status_code, status.HTTP_200_OK)

            # Download document from pre-signed s3 generated url
            s3_url = data['meta']['presigned_s3']
            res = requests.get(s3_url)
            with open('./tests/tmp/from_presigned_s3_url.pdf', 'wb') as f:
                f.write(res.content)

            # Second pdf document
            f_path = './tests/tmp/second_test_upload.pdf'
            message = "Second upload pdf test. This should be larger in size!"
            self.make_pdf_file(f_path, message=message)
            file_data, content_type = create_form_content({
                'name': os.path.basename(f_path),
                'document_type': 'Bol',
                'file_type': 'Pdf'
            })

            response = self.client.post(url, file_data, content_type=content_type)
            self.assertEqual(response.status_code, status.HTTP_201_CREATED)
            document = Document.objects.all().order_by('created_at')
            self.assertEqual(document.count(), 2)

            # Update second uploaded document status to complete
            url_patch = url + f'/{document[1].id}/'
            file_data, content_type = create_form_content({
                'upload_status': 'Complete',
            })

            response = self.client.patch(url_patch, file_data, content_type=content_type)
            data = response.json()['data']

            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertEqual(document[1].upload_status, UploadStatus.COMPLETE)
            self.assertTrue(isinstance(data['meta']['presigned_s3'], str))

            # Get list of documents
            response = self.client.get(url)
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            data = response.json()['data']

            # Assert that the list documents are in descending order
            creation_object1_date = parse(data[0]['attributes']['created_at'])
            creation_object2_date = parse(data[1]['attributes']['created_at'])
            self.assertTrue(creation_object2_date < creation_object1_date)

            # Get list of pdf documents via query params, it should return 2 elements
            url_pdf = url + '?file_type=Pdf'
            response = self.client.get(url_pdf)
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertEqual(len(data), 2)

            # Querying for png files should return an empty list at this stage
            url_png = url + '?file_type=Png'
            response = self.client.get(url_png)
            data = response.json()['data']
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertEqual(len(data), 0)

            # Get list of BOL documents via query params, it should return 2 elements
            url_bol = url + '?document_type=Bol'
            response = self.client.get(url_bol)
            data = response.json()['data']
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertEqual(len(data), 2)

            # Querying for file objects with upload_status FAILED, should return an empty list at this stage
            url_failed_satus = url + '?upload_status=FAIled'
            response = self.client.get(url_failed_satus)
            data = response.json()['data']
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertEqual(len(data), 0)


class DocumentAPITests(APITestCase):

    def setUp(self):

        # Disable Shipment post save signal
        signals.post_save.disconnect(sender=Shipment, dispatch_uid='shipment_post_save')

        self.user_1 = passive_credentials_auth(get_jwt(username='user1@shipchain.io', sub=FAKE_ID))
        self.shipper_user = passive_credentials_auth(get_jwt(username='user2@shipchain.io', sub=SHIPPER_ID))
        self.carrier_user = passive_credentials_auth(get_jwt(username='user3@shipchain.io', sub=MODERATOR_ID))
        self.moderator_user = passive_credentials_auth(get_jwt(username='user4@shipchain.io', sub=CARRIER_ID))
        self.another_user = passive_credentials_auth(get_jwt(username='user4@shipchain.io', sub=ANOTHER_ID))

        shipment = Shipment.objects.create(
            vault_id=VAULT_ID,
            carrier_wallet_id=CARRIER_WALLET_ID,
            shipper_wallet_id=SHIPPER_WALLET_ID,
            storage_credentials_id=STORAGE_CRED_ID,
            owner_id=FAKE_ID
        )

        shipment_2 = Shipment.objects.create(
            vault_id=VAULT_ID,
            carrier_wallet_id=CARRIER_WALLET_ID,
            shipper_wallet_id=SHIPPER_WALLET_ID,
            storage_credentials_id=STORAGE_CRED_ID,
            owner_id=FAKE_ID
        )

        LoadShipment.objects.create(shipment=shipment,
                                    funding_type=Shipment.FUNDING_TYPE,
                                    contracted_amount=Shipment.SHIPMENT_AMOUNT)

        # Re-enable Shipment post save signal
        signals.post_save.connect(shipment_post_save, sender=Shipment, dispatch_uid='shipment_post_save')

        self.data = [
            {'document_type': DocumentType.BOL, 'file_type': FileType.PDF, 'shipment': shipment,
             'upload_status': UploadStatus.PENDING, 'owner_id': self.user_1.id},
            {'document_type': DocumentType.BOL, 'file_type': FileType.PNG, 'shipment': shipment,
             'upload_status': UploadStatus.COMPLETE, 'owner_id': self.user_1.id},
            {'document_type': DocumentType.OTHER, 'file_type': FileType.JPEG, 'shipment': shipment,
             'upload_status': UploadStatus.COMPLETE, 'owner_id': self.user_1.id},
            {'document_type': DocumentType.OTHER, 'file_type': FileType.PDF, 'shipment': shipment,
             'upload_status': UploadStatus.COMPLETE, 'owner_id': self.shipper_user.id},
            {'document_type': DocumentType.OTHER, 'file_type': FileType.PDF, 'shipment': shipment_2,
             'upload_status': UploadStatus.COMPLETE, 'owner_id': self.shipper_user.id},
        ]

        self.shipments = [shipment, shipment_2, ]

    def set_user(self, user, token=None):
        self.client.force_authenticate(user=user, token=token)

    def create_documents(self):

        self.pdf_docs = []
        for d in self.data:
            self.pdf_docs.append(
                Document.objects.create(**d)
            )

    def test_create_objects(self):
        self.create_documents()
        self.assertEqual(Document.objects.all().count(), 5)

    def test_s3_notification(self):
        url = reverse('document-events', kwargs={'version': 'v1'})

        self.set_user(None)

        # S3 Lambda PutObject event: https://docs.aws.amazon.com/lambda/latest/dg/eventsources.html#eventsources-s3-put
        s3_event = {"Records": [{"s3": {
            "bucket": {"name": "document-management-s3-local"}, "object": {"key": "api-cloudfront.json"}
        }}]}

        # Bad auth
        response = self.client.post(url, json.dumps(s3_event), content_type="application/json")
        assert response.status_code == status.HTTP_403_FORBIDDEN

        with mock.patch.object(requests.Session, 'post') as mock_method:
            mock_method.return_value = mocked_rpc_response({
                "jsonrpc": "2.0",
                "result": {
                    "success": True,
                    "vault_signed": {
                        'hash': VAULT_HASH
                    }
                },
                "id": 0
            })

            # Test improper key formatting
            response = self.client.post(url, json.dumps(s3_event), content_type="application/json",
                                        X_NGINX_SOURCE='internal', X_SSL_CLIENT_VERIFY='SUCCESS',
                                        X_SSL_CLIENT_DN='/CN=document-management-s3-hook.test-internal')
            assert response.status_code == status.HTTP_400_BAD_REQUEST

            # Test 'good' key with no document
            "sc_uuid/wallet_uuid/vault_uuid/document_uuid.ext"
            s3_event["Records"][0]["s3"]["object"]["key"] = f"{FAKE_ID}/{FAKE_ID}/{FAKE_ID}/{FAKE_ID}.png"
            response = self.client.post(url, json.dumps(s3_event), content_type="application/json",
                                        X_NGINX_SOURCE='internal', X_SSL_CLIENT_VERIFY='SUCCESS',
                                        X_SSL_CLIENT_DN='/CN=document-management-s3-hook.test-internal')
            assert response.status_code == status.HTTP_400_BAD_REQUEST

            # Test that a real document has its upload status updated
            doc = Document.objects.create(**self.data[0])
            assert doc.upload_status == UploadStatus.PENDING
            s3_event["Records"][0]["s3"]["object"]["key"] = f"{FAKE_ID}/{FAKE_ID}/{FAKE_ID}/{doc.id}.png"
            response = self.client.post(url, json.dumps(s3_event), content_type="application/json",
                                        X_NGINX_SOURCE='internal', X_SSL_CLIENT_VERIFY='SUCCESS',
                                        X_SSL_CLIENT_DN='/CN=document-management-s3-hook.test-internal')
            assert response.status_code == status.HTTP_204_NO_CONTENT
            doc.refresh_from_db()
            assert mock_method.call_count == 1
            assert doc.upload_status == UploadStatus.COMPLETE

    def test_document_permission(self):

        url = reverse('shipment-documents-list', kwargs={'version': 'v1', 'shipment_pk': self.shipments[0].id})

        self.create_documents()

        file_data = {
            'name': 'Test Permission',
            'document_type': 'Image',
            'file_type': 'Png'
        }

        self.set_user(self.user_1)

        with mock.patch('apps.permissions.IsShipperMixin.has_shipper_permission') as mock_is_shipper, \
                mock.patch('apps.permissions.IsCarrierMixin.has_carrier_permission') as mock_is_carrier, \
                mock.patch('apps.permissions.IsModeratorMixin.has_moderator_permission') as mock_is_moderator, \
                mock.patch.object(requests.Session, 'post') as mock_rpc_call:

            mock_rpc_call.return_value = mocked_rpc_response({
                "jsonrpc": "2.0",
                "result": {
                    "success": True,
                },
                "id": 0
            })

            # user_1 is the shipment owner, he should have access to all 4 documents
            response = self.client.get(url)
            data = response.json()['data']
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertEqual(len(data), 4)

            mock_is_shipper.return_value = True
            mock_is_carrier.return_value = False
            mock_is_moderator.return_value = False

            # shipper_user is the  shipment's shipper, he should have access to all 4 shipment's documents
            self.set_user(self.shipper_user)
            response = self.client.get(url)
            data = response.json()['data']
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertEqual(len(data), 4)
            self.assertEqual(mock_is_shipper.call_count, 1)
            self.assertEqual(mock_is_carrier.call_count, 0)
            self.assertEqual(mock_is_moderator.call_count, 0)

            # carrier_user is the shipment's carrier, he should have access to all 4 shipment's documents
            self.set_user(self.carrier_user)
            mock_is_shipper.return_value = False
            mock_is_carrier.return_value = True
            response = self.client.get(url)
            data = response.json()['data']
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertEqual(len(data), 4)
            self.assertEqual(mock_is_shipper.call_count, 2)
            self.assertEqual(mock_is_carrier.call_count, 1)
            self.assertEqual(mock_is_moderator.call_count, 0)

            # moderator_user is the shipment's moderator, he should have access to all 4 shipment's documents
            self.set_user(self.moderator_user)
            mock_is_carrier.return_value = False
            mock_is_moderator.return_value = True
            response = self.client.get(url)
            data = response.json()['data']
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertEqual(len(data), 4)
            self.assertEqual(mock_is_shipper.call_count, 3)
            self.assertEqual(mock_is_carrier.call_count, 2)
            self.assertEqual(mock_is_moderator.call_count, 1)

            # another_user is none of shipment owner, shipper, carrier or moderator.
            # He shouldn't have access to the shipment's documents
            self.set_user(self.another_user)
            mock_is_moderator.return_value = False
            response = self.client.get(url)
            # data = response.json()['data']
            self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
            # self.assertEqual(len(data), 4)
            self.assertEqual(mock_is_shipper.call_count, 4)
            self.assertEqual(mock_is_carrier.call_count, 3)
            self.assertEqual(mock_is_moderator.call_count, 2)

            mock_is_shipper.reset_mock()
            mock_is_carrier.reset_mock()
            mock_is_moderator.reset_mock()

            mock_is_shipper.return_value = True
            mock_is_carrier.return_value = False
            mock_is_moderator.return_value = False

            # The shipper should be able to upload a document
            # This is equivalently valid for carrier and moderator
            self.set_user(self.shipper_user)
            response = self.client.post(url, file_data, format='json')
            self.assertEqual(response.status_code, status.HTTP_201_CREATED)
            self.assertEqual(mock_is_shipper.call_count, 1)
            self.assertEqual(mock_is_carrier.call_count, 0)
            self.assertEqual(mock_is_moderator.call_count, 0)


class ImageDocumentViewSetAPITests(APITestCase):

    def setUp(self):
        self.client = APIClient()

        # Disable Shipment post save signal
        signals.post_save.disconnect(sender=Shipment, dispatch_uid='shipment_post_save')

        self.user_1 = passive_credentials_auth(get_jwt(username='user1@shipchain.io', sub=OWNER_ID))

        self.shipment = Shipment.objects.create(
            id=SHIPMENT_ID,
            vault_id=VAULT_ID,
            carrier_wallet_id=CARRIER_WALLET_ID,
            shipper_wallet_id=SHIPPER_WALLET_ID,
            storage_credentials_id=STORAGE_CRED_ID,
            owner_id=OWNER_ID
        )

        # Re-enable Shipment post save signal
        signals.post_save.connect(shipment_post_save, sender=Shipment, dispatch_uid='shipment_post_save')

        # Upload bucket creation
        self.s3_resource = settings.S3_RESOURCE

        # Buckets clean up
        for bucket in self.s3_resource.buckets.all():
            for key in bucket.objects.all():
                key.delete()
            bucket.delete()

        try:
            self.s3_resource.create_bucket(Bucket=settings.DOCUMENT_MANAGEMENT_BUCKET)
        except Exception as exc:
            pass

    def tearDown(self):
        files = glob.glob('./tests/tmp/*.*')
        for f in files:
            os.remove(f)

    def set_user(self, user, token=None):
        self.client.force_authenticate(user=user, token=token)

    def make_image(self, file_path, size=(600, 300), message=None):
        default_message = 'Shipchain Transmission.'
        text = message if message else default_message
        img = Image.new('RGB', size, color=(252, 128, 67))
        font1 = ImageFont.truetype('tests/data/font.ttf', 35)
        font2 = ImageFont.truetype('tests/data/font2.ttf', 35)
        draw = ImageDraw.Draw(img)
        draw.text((30, 115), text, font=font1, fill='white')
        draw.text((160, 150), DATE, font=font2, fill='white')
        img.save(file_path)

    def test_image_creation(self):
        img_path = ['./tests/tmp/jpeg_img.jpg', './tests/tmp/png_img.png']

        for img in img_path:
            self.make_image(img)

        url = reverse('shipment-documents-list', kwargs={'version': 'v1', 'shipment_pk': self.shipment.id})

        file_data, content_type = create_form_content({
            'name': os.path.basename(img_path[1]),
            'document_type': 'Image',
            'file_type': 'Png'
        })

        # png image object creation
        self.set_user(self.user_1)
        response = self.client.post(url, file_data, content_type=content_type)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        document = Document.objects.all()
        self.assertEqual(document.count(), 1)

        data = response.json()['data']
        self.assertEqual(data['attributes']['file_type'], str(FileType.PNG))
        fields = data['meta']['presigned_s3']['fields']

        # File upload
        put_url = data['meta']['presigned_s3']['url']
        with open(img_path[1], 'rb') as png:
            res = requests.post(put_url, data=fields, files={'file': png})

        self.assertEqual(res.status_code, status.HTTP_204_NO_CONTENT)

        # Failed upload document and Pending should have the presigned post meta object
        url_patch = url + f'/{document[0].id}/'
        file_data, content_type = create_form_content({
            'upload_status': 'Failed',
        })
        response = self.client.patch(url_patch, file_data, content_type=content_type)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()['data']
        self.assertEqual(document[0].upload_status, UploadStatus.FAILED)
        self.assertTrue(isinstance(data['meta']['presigned_s3'], dict))

        # Update document object upon upload completion
        file_data, content_type = create_form_content({
            'upload_status': 'complete',
        })
        with mock.patch.object(requests.Session, 'post') as mock_method:
            mock_method.return_value = mocked_rpc_response({
                "jsonrpc": "2.0",
                "result": {
                    "success": True,
                },
                "id": 0
            })
            response = self.client.patch(url_patch, file_data, content_type=content_type)
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            data = response.json()['data']
            self.assertEqual(document[0].upload_status, UploadStatus.COMPLETE)
            self.assertTrue(isinstance(data['meta']['presigned_s3'], str))

            # Get a document
            url_get = url + f'/{document[0].id}/'
            response = self.client.get(url_get)
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            data = response.json()['data']
            self.assertTrue(data['meta']['presigned_s3'])

            # Download document from pre-signed s3 generated url
            s3_url = data['meta']['presigned_s3']
            res = requests.get(s3_url)
            with open('./tests/tmp/png_img_from_presigned_s3_url.png', 'wb') as f:
                f.write(res.content)

            # Get list of png image via query params, should return one document
            url_png = url + '?file_type=Png'
            response = self.client.get(url_png)
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            data = response.json()['data']
            self.assertEqual(len(data), 1)

            # This should return an empty list since there is no pdf in db at this stage
            url_pdf = url + '?file_type=Pdf'
            response = self.client.get(url_pdf)
            data = response.json()['data']
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertEqual(len(data), 0)

    def test_get_document_from_vault(self):
        img_path = './tests/tmp/png_img.png'

        self.make_image(img_path)

        # url = reverse('document-list', kwargs={'version': 'v1'})
        url = reverse('shipment-documents-list', kwargs={'version': 'v1', 'shipment_pk': self.shipment.id})

        file_data, content_type = create_form_content({
            'name': os.path.basename(img_path),
            'document_type': 'Image',
            'file_type': 'Png'
        })

        with mock.patch.object(requests.Session, 'post') as mock_method:
            mock_method.return_value = mocked_rpc_response({
                "jsonrpc": "2.0",
                "result": {
                    "success": True,
                    "vault_signed": {
                        'hash': VAULT_HASH
                    }
                },
                "id": 0
            })

            self.set_user(self.user_1)
            # png image object creation
            response = self.client.post(url, file_data, content_type=content_type)
            self.assertEqual(response.status_code, status.HTTP_201_CREATED)

            # The document status is pending, we won't try to retrieved from vault
            data = response.json()['data']
            self.assertEqual(data['attributes']['upload_status'], 'PENDING')
            # The rpc_client.put_document_in_s3 is not csalled
            assert mock_method.call_count == 0

            document = Document.objects.get(id=data['id'])
            document.upload_status = UploadStatus.COMPLETE
            document.save()

            # Document upload
            put_url = data['meta']['presigned_s3']['url']
            fields = data['meta']['presigned_s3']['fields']
            with open(img_path, 'rb') as png:
                res = requests.post(put_url, data=fields, files={'file': png})

            self.assertEqual(res.status_code, status.HTTP_204_NO_CONTENT)

            # The document has been uploaded and its status is COMPLETE.
            # the rpc_client.put_document_in_s3 should not be called
            response = self.client.get(url)
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            assert mock_method.call_count == 0

            doc = Document.objects.all().first()
            self.s3_resource.Object(settings.DOCUMENT_MANAGEMENT_BUCKET, doc.s3_key).delete()

            # The file has been deleted from the bucket.
            self.assertEqual(
                len(list(self.s3_resource.Bucket(settings.DOCUMENT_MANAGEMENT_BUCKET).objects.filter(Prefix=doc.s3_key))),
                0
            )

            # The file object status is COMPLETE but the file is no longueur in the bucket.
            # the rpc_client.put_document_in_s3 should be invoked
            response = self.client.get(url)
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            assert mock_method.call_count == 1

            # trying to access a list of documents, the rpc method should be called for each of the COMPLETE objects
            # with file missing from s3. Here twice exactly
            file_data = {
                'name': 'Second file',
                'document_type': DocumentType.BOL,
                'file_type': FileType.PDF,
                'shipment_id': self.shipment.id,
                'upload_status': UploadStatus.COMPLETE,
                'owner_id': self.user_1.id
            }
            Document.objects.create(**file_data)

            response = self.client.get(url)
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            assert mock_method.call_count == 3

            # Trying to access the COMPLETE document detail the rpc method should be called
            url_get = url + f'/{doc.id}/'
            response = self.client.patch(url_get, {}, content_type='application/json')
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            assert mock_method.call_count == 4

            # In case of rpc error, we should have a null presigned_url
            mock_method.return_value = mocked_rpc_response({
                "jsonrpc": "2.0",
                "result": {
                    "success": False,
                },
                "id": 0
            })

            response = self.client.get(url_get)
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            data = response.json()['data']
            self.assertIsNone(data['meta']['presigned_s3'])
