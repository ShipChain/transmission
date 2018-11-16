import copy
from unittest import mock
from pathlib import Path
import datetime

import requests
import boto
import boto3
from botocore.client import Config
from minio import Minio
import jwt
import json
from fpdf import FPDF

from django.db.models import signals
from django.conf import settings
from rest_framework import status
from rest_framework.reverse import reverse
from rest_framework.test import APITestCase, APIClient, force_authenticate
from jose import jws
from moto import mock_s3
import httpretty
import json
import os
import re
from unittest.mock import patch

from apps.shipments.models import Shipment
from apps.shipments.signals import shipment_post_save
from apps.documents.models import Document, UploadStatus
from apps.authentication import AuthenticatedUser
from apps.utils import random_string
from apps.utils import random_id, get_s3_client
from tests.utils import create_form_content


VAULT_ID = 'b715a8ff-9299-4c87-96de-a4b0a4a54509'
CARRIER_WALLET_ID = '3716ff65-3d03-4b65-9fd5-43d15380cff9'
SHIPPER_WALLET_ID = '48381c16-432b-493f-9f8b-54e88a84ec0a'
STORAGE_CRED_ID = '77b72202-5bcd-49f4-9860-bc4ec4fee07b'
DEVICE_ID = '332dc6c8-b89e-449e-a802-0bfe760f83ff'


class DocumentViewSetAPITests(APITestCase):

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
            vault_id=VAULT_ID,
            carrier_wallet_id=CARRIER_WALLET_ID,
            shipper_wallet_id=SHIPPER_WALLET_ID,
            storage_credentials_id=STORAGE_CRED_ID,
            owner_id='5e8f1d76-162d-4f21-9b71-2ca97306ef7c'
        )

    def set_user(self, user, token=None):
        self.client.force_authenticate(user=user, token=token)

    def make_pdf_file(self, file_path):
        date = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font('Arial', 'B', 20)
        pdf.cell(40, 10, f"Hey There Welcome to Shipchain Transmission.")
        pdf.cell(40, 60, f"{date}")
        pdf.output(file_path, 'F')

    def test_sign_to_s3(self):
        # Re-enable Shipment post save signal
        signals.post_save.connect(shipment_post_save, sender=Shipment, dispatch_uid='shipment_post_save')

        url = reverse('document-list', kwargs={'version': 'v1'})

        f_path = './test_upload.pdf'
        self.make_pdf_file(f_path)

        file_data, content_type = create_form_content({
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
        print(f">>> s3_path: {document[0].s3_path}")
        print(f'>>>> Data: {response.data}')
        # print(f">>> Shipment_id: {document[0].shipment.id}")
        self.assertEqual(self.shipment.id, document[0].shipment_id)

        # Check s3 path integrity in db
        s3_path = f"{settings.S3_BUCKET}/{document[0].shipment.id}/{document[0].id}.pdf"
        self.assertEqual(document[0].s3_path, s3_path)

        data = json.loads(response.json()['data'])['data']['fields']
        print(data)
        _, s3_resource = get_s3_client()

        for bucket in s3_resource.buckets.all():
            for key in bucket.objects.all():
                key.delete()
            bucket.delete()

        # Upload bucket creation
        s3_resource.create_bucket(Bucket=settings.S3_BUCKET)

        # File upload
        put_url = f"{settings.SCHEMA}{settings.S3_HOST}/{settings.S3_BUCKET}"
        with open(f_path, 'rb') as pdf:
            res = requests.post(put_url, data=data, files={'file': pdf})

        self.assertEqual(res.status_code, status.HTTP_204_NO_CONTENT)
        s3_resource.Bucket(settings.S3_BUCKET).download_file(data['key'], './downloaded.pdf')

        # We verify the integrity of the uploaded file
        downloaded_file = Path('./downloaded.pdf')
        self.assertTrue(downloaded_file.exists())

        # Update document object upon upload completion
        url = reverse('document-detail', kwargs={'version': 'v1', 'pk': document[0].id})
        file_data, content_type = create_form_content({
            'upload_status': 1,
            'shipment_id': self.shipment.id
        })

        response = self.client.put(url, file_data, content_type=content_type)
        print(response.data)
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        self.assertEqual(document[0].upload_status, UploadStatus.COMPLETED)

        # Update of document upload failed
        file_data, content_type = create_form_content({
            'upload_status': 2,
            'shipment_id': self.shipment.id
        })
        response = self.client.put(url, file_data, content_type=content_type)
        print(response.data)
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        self.assertEqual(document[0].upload_status, UploadStatus.FAILED)

        # Tentative to update a fields than upload_status should fail
        file_data, content_type = create_form_content({
            'document_type': 1,
            'shipment_id': self.shipment.id,
            # 'upload_status': 1,
        })
        response = self.client.put(url, file_data, content_type=content_type)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(document[0].upload_status, UploadStatus.FAILED)

        # Get a document
        url = reverse('document-detail', kwargs={'version': 'v1', 'pk': document[0].id})
        response = self.client.get(url)
        print(response.data)
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)

        # Download document from pre-signed s3 generated url
        s3_url = response.data['s3_url']
        res = requests.get(s3_url)
        print(res.url)
        with open('./from_presigned_s3_url.pdf', 'wb') as f:
            f.write(res.content)

        # Get list of documents
        url = reverse('document-list', kwargs={'version': 'v1'})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # #### Disable Shipment post save signal for unit testing purposes ####
        signals.post_save.disconnect(sender=Shipment, dispatch_uid='shipment_post_save')

        # Trying to access a document after delivery should fail
        self.shipment.delivery_actual = datetime.datetime.now() - datetime.timedelta(days=11)
        self.shipment.save()

        # #### Re-enable Shipment post save signal ####
        signals.post_save.connect(shipment_post_save, sender=Shipment, dispatch_uid='shipment_post_save')

        print(self.shipment.delivery_actual)
        url = reverse('document-detail', kwargs={'version': 'v1', 'pk': document[0].id})
        response = self.client.get(url)
        print(response.data)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        # Thus should fail
        # failed_file_path = f'./{random_string()}.txt'
        # with open(failed_file_path, 'w') as txt:
        #     txt.write('Hello World!!!')

        # with open(failed_file_path, 'rb') as failed:
        #     res = requests.post(put_url, data=data, files={'file': failed})
        #     self.assertNotEqual(res.status_code, 204)

        # s3.Bucket(settings.S3_BUCKET).upload_file('./test.txt', 'test.txt')
        # s3.Bucket(settings.S3_BUCKET).upload_file(f_path, 'nested/' + f_path.split('./')[-1])


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
        s3_path = 'https://devcenter.heroku.com/articles/s3-upload-python'
        self.data = [
            {'document_type': 0, 'file_type': 0, 'size': 9000000, 'shipment': shipment, 's3_path': s3_path},
        ]

    def create_docs_data(self):

        # Re-enable Shipment post save signal
        signals.post_save.connect(shipment_post_save, sender=Shipment, dispatch_uid='shipment_post_save')

        self.pdf_docs = []
        for d in self.data:
            self.pdf_docs.append(
                Document.objects.create(**d)
            )

    def test_create_objects(self):
        self.create_docs_data()
        self.assertEqual(Document.objects.all().count(), 1)
