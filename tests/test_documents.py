from pathlib import Path
import datetime

import requests
from fpdf import FPDF
from PIL import Image, ImageDraw, ImageFont

from django.db.models import signals
from django.conf import settings
from rest_framework import status
from rest_framework.reverse import reverse
from rest_framework.test import APITestCase, APIClient, force_authenticate

import os

from apps.shipments.models import Shipment
from apps.shipments.signals import shipment_post_save
from apps.documents.models import Document, UploadStatus
from apps.authentication import AuthenticatedUser
from apps.utils import get_s3_client
from tests.utils import create_form_content

SHIPMENT_ID = 'Shipment-Custom-Id-{}'
VAULT_ID = 'b715a8ff-9299-4c87-96de-a4b0a4a54509'
CARRIER_WALLET_ID = '3716ff65-3d03-4b65-9fd5-43d15380cff9'
SHIPPER_WALLET_ID = '48381c16-432b-493f-9f8b-54e88a84ec0a'
STORAGE_CRED_ID = '77b72202-5bcd-49f4-9860-bc4ec4fee07b'
DEVICE_ID = '332dc6c8-b89e-449e-a802-0bfe760f83ff'
DATE = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
SHIPMENT_ID = SHIPMENT_ID.format(DATE[:10])


class PdfDocumentViewSetAPITests(APITestCase):

    def setUp(self):
        self.client = APIClient()

        # Disable Shipment post save signal
        signals.post_save.disconnect(sender=Shipment, dispatch_uid='shipment_post_save')

        self.user_1 = AuthenticatedUser({
            'user_id': '5e8f1d76-162d-4f21-9b71-2ca97306ef7c',
            'username': 'user1@shipchain.io',
            'email': 'user1@shipchain.io',
        })

        self.shipment = Shipment.objects.create(
            id=SHIPMENT_ID,
            vault_id=VAULT_ID,
            carrier_wallet_id=CARRIER_WALLET_ID,
            shipper_wallet_id=SHIPPER_WALLET_ID,
            storage_credentials_id=STORAGE_CRED_ID,
            owner_id='5e8f1d76-162d-4f21-9b71-2ca97306ef7c'
        )

        # Re-enable Shipment post save signal
        signals.post_save.connect(shipment_post_save, sender=Shipment, dispatch_uid='shipment_post_save')

        _, s3_resource = get_s3_client()

        for bucket in s3_resource.buckets.all():
            for key in bucket.objects.all():
                key.delete()
            bucket.delete()

        try:
            s3_resource.create_bucket(Bucket=settings.S3_BUCKET)
        except Exception as exc:
            pass

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
        url = reverse('document-list', kwargs={'version': 'v1'})

        f_path = './test_upload.pdf'
        self.make_pdf_file(f_path)

        file_data, content_type = create_form_content({
            'name': 'Test BOL',
            'description': 'Auto generated file for test purposes',
            'document_type': 0,
            'file_type': 0,
            'size': os.path.getsize(f_path),
            'upload_status': 0,
            'shipment_id': self.shipment.id
        })

        # Unauthenticated user should fail
        response = self.client.post(url, file_data, content_type=content_type)
        self.assertNotEqual(response.status_code, status.HTTP_201_CREATED)

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
        wallet_id = shipment.shipper_wallet_id
        storage_credentials_id = shipment.storage_credentials_id
        vault_id = shipment.vault_id
        s3_path = f"s3://{settings.S3_BUCKET}/{storage_credentials_id}/{wallet_id}/{vault_id}/{doc_id}.pdf"
        self.assertEqual(document[0].s3_path, s3_path)

        data = response.json()['data']['data']
        fields = data['fields']
        _, s3_resource = get_s3_client()

        # File upload
        put_url = data['url']
        with open(f_path, 'rb') as pdf:
            res = requests.post(put_url, data=fields, files={'file': pdf})

        self.assertEqual(res.status_code, status.HTTP_204_NO_CONTENT)
        s3_resource.Bucket(settings.S3_BUCKET).download_file(fields['key'], './downloaded.pdf')

        # We verify the integrity of the uploaded file
        downloaded_file = Path('./downloaded.pdf')
        self.assertTrue(downloaded_file.exists())

        # Update document object upon upload completion
        url = reverse('document-detail', kwargs={'version': 'v1', 'pk': document[0].id})
        file_data, content_type = create_form_content({
            'upload_status': 1,
        })
        response = self.client.put(url, file_data, content_type=content_type)
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        self.assertEqual(document[0].upload_status, UploadStatus.COMPLETED)

        # Tentative to update a fields other than upload_status should fail
        file_data, content_type = create_form_content({
            'document_type': 1,
            'shipment_id': self.shipment.id,
            # 'upload_status': 1,
        })
        response = self.client.put(url, file_data, content_type=content_type)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(document[0].upload_status, UploadStatus.COMPLETED)

        # Get a document
        url = reverse('document-detail', kwargs={'version': 'v1', 'pk': document[0].id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)

        # Download document from pre-signed s3 generated url
        s3_url = response.data['url']
        res = requests.get(s3_url)
        with open('./from_presigned_s3_url.pdf', 'wb') as f:
            f.write(res.content)

        # Second pdf document
        f_path = './second_test_upload.pdf'
        message = "Second upload pdf test. This should be larger in size!"
        self.make_pdf_file(f_path, message=message)
        file_data, content_type = create_form_content({
            'document_type': 0,
            'file_type': 0,
            'size': os.path.getsize(f_path),
            'upload_status': 0,
            'shipment_id': self.shipment.id
        })
        url = reverse('document-list', kwargs={'version': 'v1'})
        response = self.client.post(url, file_data, content_type=content_type)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        document = Document.objects.all()
        self.assertEqual(document.count(), 2)

        # Get the second uploaded document should fail, its upload status is not set to complete
        url = reverse('document-detail', kwargs={'version': 'v1', 'pk': document[1].id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        # Update second uploaded document status to completed
        url = reverse('document-detail', kwargs={'version': 'v1', 'pk': document[1].id})
        file_data, content_type = create_form_content({
            'upload_status': 1,
        })
        response = self.client.put(url, file_data, content_type=content_type)
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        self.assertEqual(document[1].upload_status, UploadStatus.COMPLETED)

        # Get list of documents
        url = reverse('document-list', kwargs={'version': 'v1'})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # # #### Disable Shipment post save signal for unit testing purposes ####
        # signals.post_save.disconnect(sender=Shipment, dispatch_uid='shipment_post_save')
        #
        # # Trying to access a document after delivery should fail
        # self.shipment.delivery_actual = datetime.datetime.now() - datetime.timedelta(days=11)
        # self.shipment.save()
        #
        # # #### Re-enable Shipment post save signal ####
        # signals.post_save.connect(shipment_post_save, sender=Shipment, dispatch_uid='shipment_post_save')
        #
        # url = reverse('document-detail', kwargs={'version': 'v1', 'pk': document[0].id})
        # response = self.client.get(url)
        # # Trying to access a document after delivery should fail
        # self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        # Get list of pdf documents via query params, it should return 2 elements
        url = reverse('document-list', kwargs={'version': 'v1'})
        url += f'?file_type=Pdf'
        response = self.client.get(url)
        data = response.json()['data']['documents']
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(data), 2)

        # Querying for png files should return an empty list at this stage
        url = reverse('document-list', kwargs={'version': 'v1'})
        url += f'?file_type=Png'
        response = self.client.get(url)
        data = response.json()['data']['documents']
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(data), 0)


class DocumentAPITests(APITestCase):

    def setUp(self):

        # Disable Shipment post save signal
        signals.post_save.disconnect(sender=Shipment, dispatch_uid='shipment_post_save')

        self.user_1 = AuthenticatedUser({
            'user_id': '5e8f1d76-162d-4f21-9b71-2ca97306ef7c',
            'username': 'user1@shipchain.io',
            'email': 'user1@shipchain.io',
        })

        shipment = Shipment.objects.create(
            vault_id=VAULT_ID,
            carrier_wallet_id=CARRIER_WALLET_ID,
            shipper_wallet_id=SHIPPER_WALLET_ID,
            storage_credentials_id=STORAGE_CRED_ID,
            owner_id='5e8f1d76-162d-4f21-9b71-2ca97306ef7c'
        )

        # Re-enable Shipment post save signal
        signals.post_save.connect(shipment_post_save, sender=Shipment, dispatch_uid='shipment_post_save')

        s3_path = 'https://devcenter.heroku.com/articles/s3-upload-python'
        self.data = [
            {'document_type': 0, 'file_type': 0, 'size': 9000000, 'shipment': shipment, 's3_path': s3_path},
        ]

    def create_docs_data(self):

        self.pdf_docs = []
        for d in self.data:
            self.pdf_docs.append(
                Document.objects.create(**d)
            )

    def test_create_objects(self):
        self.create_docs_data()
        self.assertEqual(Document.objects.all().count(), 1)


class ImageDocumentViewSetAPITests(APITestCase):

    def setUp(self):
        self.client = APIClient()

        # Disable Shipment post save signal
        signals.post_save.disconnect(sender=Shipment, dispatch_uid='shipment_post_save')

        self.user_1 = AuthenticatedUser({
            'user_id': '5e8f1d76-162d-4f21-9b71-2ca97306ef7c',
            'username': 'user1@shipchain.io',
            'email': 'user1@shipchain.io',
        })

        self.shipment = Shipment.objects.create(
            id=SHIPMENT_ID,
            vault_id=VAULT_ID,
            carrier_wallet_id=CARRIER_WALLET_ID,
            shipper_wallet_id=SHIPPER_WALLET_ID,
            storage_credentials_id=STORAGE_CRED_ID,
            owner_id='5e8f1d76-162d-4f21-9b71-2ca97306ef7c'
        )

        # Re-enable Shipment post save signal
        signals.post_save.connect(shipment_post_save, sender=Shipment, dispatch_uid='shipment_post_save')

        # Upload bucket creation
        _, s3_resource = get_s3_client()

        try:
            s3_resource.create_bucket(Bucket=settings.S3_BUCKET)
        except Exception as exc:
            pass

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
        img_path = ['./jpeg_img.jpg', './png_img.png']

        for img in img_path:
            self.make_image(img)

        url = reverse('document-list', kwargs={'version': 'v1'})

        file_data, content_type = create_form_content({
            'document_type': 1,
            'file_type': 2,
            'size': os.path.getsize(img_path[1]),
            'upload_status': 0,
            'shipment_id': self.shipment.id
        })

        # png image object creation
        self.set_user(self.user_1)
        response = self.client.post(url, file_data, content_type=content_type)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        document = Document.objects.all()
        self.assertEqual(document.count(), 1)

        data = response.json()['data']['data']
        fields = data['fields']
        _, s3_resource = get_s3_client()

        # File upload
        put_url = data['url']
        with open(img_path[1], 'rb') as png:
            res = requests.post(put_url, data=fields, files={'file': png})

        self.assertEqual(res.status_code, status.HTTP_204_NO_CONTENT)

        # Update document object upon upload completion
        url = reverse('document-detail', kwargs={'version': 'v1', 'pk': document[0].id})
        file_data, content_type = create_form_content({
            'upload_status': 1,
        })
        response = self.client.put(url, file_data, content_type=content_type)
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        self.assertEqual(document[0].upload_status, UploadStatus.COMPLETED)

        # Get a document
        url = reverse('document-detail', kwargs={'version': 'v1', 'pk': document[0].id})
        response = self.client.get(url)
        data = response.json()['data']
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        self.assertTrue('url' in data.keys())

        # Download document from pre-signed s3 generated url
        s3_url = data['url']
        res = requests.get(s3_url)
        with open('./png_img_from_presigned_s3_url.png', 'wb') as f:
            f.write(res.content)

        # Get list of png image via query params, should return one document
        url = reverse('document-list', kwargs={'version': 'v1'})
        url += '?file_type=Png'
        response = self.client.get(url)
        data = response.json()['data']['documents']
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(data), 1)

        # This should return an empty list since there is no pdf in db at this stage
        url = reverse('document-list', kwargs={'version': 'v1'})
        url += '?file_type=Pdf'
        response = self.client.get(url)
        data = response.json()['data']['documents']
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(data), 0)
