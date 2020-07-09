import glob
from datetime import datetime
from unittest import mock

import os
import requests
from django.conf import settings
from django.urls import reverse
from pytest import fixture
from shipchain_common.test_utils import AssertionHelper, mocked_rpc_response
from shipchain_common.utils import random_id

from apps.documents.models import FileType, DocumentType
from apps.utils import UploadStatus


class TestDocumentsCreate:
    @fixture(autouse=True)
    def set_up(self, shipment_alice, shipment_alice_two, mocked_engine_rpc):
        self.shipment_alice_url = reverse('shipment-documents-list',
                                          kwargs={'version': 'v1', 'shipment_pk': shipment_alice.id})
        self.shipment_alice_two_url = reverse('shipment-documents-list',
                                              kwargs={'version': 'v1', 'shipment_pk': shipment_alice_two.id})
        self.shipment_random_url = reverse('shipment-documents-list',
                                           kwargs={'version': 'v1', 'shipment_pk': random_id()})

    def test_requires_authentication(self, api_client):
        response = api_client.post(self.shipment_alice_url, {
            'name': 'Test BOL',
            'document_type': 'Bol',
            'file_type': 'Pdf'
        })
        AssertionHelper.HTTP_403(response)

    def test_requires_shipment_access(self, client_bob, mock_non_wallet_owner_calls,
                                      nonsuccessful_wallet_owner_calls_assertions):
        response = client_bob.post(self.shipment_alice_url, {
            'name': 'Test BOL',
            'document_type': 'Bol',
            'file_type': 'Pdf'
        })
        AssertionHelper.HTTP_403(response)
        mock_non_wallet_owner_calls.assert_calls(nonsuccessful_wallet_owner_calls_assertions)

    def test_shipment_wallet_permission(self, client_bob, mock_successful_wallet_owner_calls,
                                        entity_ref_shipment_alice, successful_wallet_owner_calls_assertions):
        attributes = {
            'name': 'Test BOL',
            'file_type': FileType.PDF.name,
            'document_type': DocumentType.AIR_WAYBILL.name
        }

        response = client_bob.post(self.shipment_alice_url, attributes)
        AssertionHelper.HTTP_201(response,
                                 entity_refs=AssertionHelper.EntityRef(
                                     resource='Document',
                                     attributes={
                                        'upload_status': UploadStatus.PENDING.name, **attributes
                                     },
                                     relationships=[{
                                         'shipment': entity_ref_shipment_alice
                                     }],
                                     meta={
                                         'presigned_s3_thumbnail': None
                                     }
                                 ))
        mock_successful_wallet_owner_calls.assert_calls(successful_wallet_owner_calls_assertions)

    def test_required_fields(self, client_alice):
        response = client_alice.post(self.shipment_alice_url, {
            'document_type': 'Bol',
            'file_type': 'Pdf'
        })
        AssertionHelper.HTTP_400(response, error='This field is required.', pointer='name')

        response = client_alice.post(self.shipment_alice_url, {
            'name': 'Test BOL',
            'file_type': 'Pdf'
        })
        AssertionHelper.HTTP_400(response, error='This field is required.', pointer='document_type')

        response = client_alice.post(self.shipment_alice_url, {
            'name': 'Test BOL',
            'document_type': 'Bol',
        })
        AssertionHelper.HTTP_400(response, error='This field is required.', pointer='file_type')

    def test_file_types(self, client_alice, entity_ref_shipment_alice):
        attributes = {
            'name': 'Test BOL',
            'file_type': 'NOT A FILE TYPE',
            'document_type': 'BOL',
        }
        response = client_alice.post(self.shipment_alice_url, attributes)
        AssertionHelper.HTTP_400(response, error=f'"{attributes["file_type"]}" is not a valid choice.',
                                 pointer='file_type')

        attributes['file_type'] = FileType.PDF.name
        response = client_alice.post(self.shipment_alice_url, attributes)
        AssertionHelper.HTTP_201(response,
                                 entity_refs=AssertionHelper.EntityRef(
                                     resource='Document',
                                     attributes={
                                        'upload_status': UploadStatus.PENDING.name, **attributes
                                     },
                                     relationships=[{
                                         'shipment': entity_ref_shipment_alice
                                     }],
                                     meta={
                                         'presigned_s3_thumbnail': None
                                     }
                                 ))
        assert isinstance(response.json()['data']['meta']['presigned_s3'], dict)

    def test_document_types(self, client_alice, entity_ref_shipment_alice):
        attributes = {
            'name': 'Test BOL',
            'file_type': 'PDF',
            'document_type': 'NOT A FILE TYPE',
        }
        response = client_alice.post(self.shipment_alice_url, attributes)
        AssertionHelper.HTTP_400(response, error=f'"{attributes["document_type"]}" is not a valid choice.',
                                 pointer='document_type')

        attributes['document_type'] = DocumentType.AIR_WAYBILL.name
        response = client_alice.post(self.shipment_alice_url, attributes)
        AssertionHelper.HTTP_201(response,
                                 entity_refs=AssertionHelper.EntityRef(
                                     resource='Document',
                                     attributes={
                                        'upload_status': UploadStatus.PENDING.name, **attributes
                                     },
                                     relationships=[{
                                         'shipment': entity_ref_shipment_alice
                                     }],
                                     meta={
                                         'presigned_s3_thumbnail': None
                                     }
                                 ))
        assert isinstance(response.json()['data']['meta']['presigned_s3'], dict)

        attributes['document_type'] = DocumentType.BOL.name
        response = client_alice.post(self.shipment_alice_url, attributes)
        AssertionHelper.HTTP_201(response,
                                 entity_refs=AssertionHelper.EntityRef(
                                     resource='Document',
                                     attributes={
                                        'upload_status': UploadStatus.PENDING.name, **attributes
                                     },
                                     relationships=[{
                                         'shipment': entity_ref_shipment_alice
                                     }],
                                     meta={
                                         'presigned_s3_thumbnail': None
                                     }
                                 ))
        assert isinstance(response.json()['data']['meta']['presigned_s3'], dict)


class TestDocumentGet:
    @fixture(autouse=True)
    def set_up(self, document_shipment_alice, document_shipment_two_alice):
        self.document_alice_url = reverse('shipment-documents-detail',
                                          kwargs={'version': 'v1',
                                                  'shipment_pk': document_shipment_alice.shipment.id,
                                                  'pk': document_shipment_alice.id})

        self.random_url = reverse('shipment-documents-detail',
                                  kwargs={'version': 'v1',
                                          'shipment_pk': document_shipment_alice.shipment.id,
                                          'pk': random_id()})

    def test_requires_authentication(self, api_client):
        response = api_client.get(self.document_alice_url)
        AssertionHelper.HTTP_403(response)

    def test_random_url_fails(self, client_alice):
        response = client_alice.get(self.random_url)
        AssertionHelper.HTTP_404(response)

    def test_wallet_calls_fail(self, client_bob, mock_non_wallet_owner_calls,
                               nonsuccessful_wallet_owner_calls_assertions):
        response = client_bob.get(self.document_alice_url)
        AssertionHelper.HTTP_403(response)
        mock_non_wallet_owner_calls.assert_calls(nonsuccessful_wallet_owner_calls_assertions)

    def test_wallet_calls_succeed(self, client_bob, mock_successful_wallet_owner_calls,
                                  successful_wallet_owner_calls_assertions, entity_ref_document_shipment_alice):
        response = client_bob.get(self.document_alice_url)
        AssertionHelper.HTTP_200(response, entity_refs=entity_ref_document_shipment_alice)
        mock_successful_wallet_owner_calls.assert_calls(successful_wallet_owner_calls_assertions)

    def test_organization_member_succeeds(self, client_carol, entity_ref_document_shipment_alice):
        response = client_carol.get(self.document_alice_url)
        AssertionHelper.HTTP_200(response, entity_refs=entity_ref_document_shipment_alice)

    def test_presigned_s3(self, client_alice, entity_ref_document_shipment_alice, mock_s3_buckets,
                          document_shipment_alice):
        document_shipment_alice.upload_status = UploadStatus.COMPLETE.name
        document_shipment_alice.save()

        assert len(list(mock_s3_buckets.Bucket(settings.DOCUMENT_MANAGEMENT_BUCKET)
                        .objects.filter(Prefix=document_shipment_alice.s3_key))) == 0
        with mock.patch.object(requests.Session, 'post') as mock_method:
            mock_method.return_value = mocked_rpc_response({
                "jsonrpc": "2.0",
                "result": {
                    "success": False,
                },
                "id": 0
            })
            response = client_alice.get(self.document_alice_url)
            entity_ref_document_shipment_alice.attributes['upload_status'] = UploadStatus.COMPLETE.name
            AssertionHelper.HTTP_200(response, entity_ref_document_shipment_alice)
            assert response.json()['data']['meta']['presigned_s3'] == None
            assert mock_method.call_count == 1


class TestDocumentDelete:
    @fixture(autouse=True)
    def set_up(self, document_shipment_alice, document_shipment_two_alice):
        self.document_alice_url = reverse('shipment-documents-detail',
                                          kwargs={'version': 'v1',
                                                  'shipment_pk': document_shipment_alice.shipment.id,
                                                  'pk': document_shipment_alice.id})

        self.random_url = reverse('shipment-documents-detail',
                                  kwargs={'version': 'v1',
                                          'shipment_pk': document_shipment_alice.shipment.id,
                                          'pk': random_id()})

    def test_requires_authentication(self, api_client):
        response = api_client.delete(self.document_alice_url)
        AssertionHelper.HTTP_403(response)

    def test_random_url_fails(self, client_alice):
        response = client_alice.delete(self.random_url)
        AssertionHelper.HTTP_405(response)

    def test_method_not_available(self, client_alice):
        response = client_alice.delete(self.document_alice_url)
        AssertionHelper.HTTP_405(response)


class TestDocumentUpdate:
    @fixture(autouse=True)
    def set_up(self, document_shipment_alice, document_shipment_two_alice):
        self.document_alice_url = reverse('shipment-documents-detail',
                                          kwargs={'version': 'v1',
                                                  'shipment_pk': document_shipment_alice.shipment.id,
                                                  'pk': document_shipment_alice.id})

        self.random_url = reverse('shipment-documents-detail',
                                  kwargs={'version': 'v1',
                                          'shipment_pk': document_shipment_alice.shipment.id,
                                          'pk': random_id()})

    def test_requires_authentication(self, api_client):
        response = api_client.patch(self.document_alice_url, {'description': 'New Description'})
        AssertionHelper.HTTP_403(response)

    def test_random_url_fails(self, client_alice):
        response = client_alice.patch(self.random_url, {'description': 'New Description'})
        AssertionHelper.HTTP_404(response)

    def test_cannot_update_type_fields(self, client_alice, entity_ref_document_shipment_alice):
        response = client_alice.patch(self.document_alice_url,
                                      {'document_type': 'New Doc Type', 'file_type': 'New File Type'})
        AssertionHelper.HTTP_200(response, entity_ref_document_shipment_alice)

    def test_authenticated_can_update(self, client_alice, client_bob, client_carol, entity_ref_document_shipment_alice,
                                      mock_successful_wallet_owner_calls, successful_wallet_owner_calls_assertions):
        response = client_alice.patch(self.document_alice_url, {'description': 'New Description'})
        entity_ref_document_shipment_alice.attributes['description'] = 'New Description'
        AssertionHelper.HTTP_200(response, entity_ref_document_shipment_alice)

        response = client_bob.patch(self.document_alice_url, {'description': 'Bob Description'})
        entity_ref_document_shipment_alice.attributes['description'] = 'Bob Description'
        AssertionHelper.HTTP_200(response, entity_ref_document_shipment_alice)
        mock_successful_wallet_owner_calls.assert_calls(successful_wallet_owner_calls_assertions)

        response = client_carol.patch(self.document_alice_url, {'description': 'Carol Description'})
        entity_ref_document_shipment_alice.attributes['description'] = 'Carol Description'
        AssertionHelper.HTTP_200(response, entity_ref_document_shipment_alice)

    def test_update_upload_status(self, client_alice, entity_ref_document_shipment_alice, mock_s3_buckets, mocker):
        response = client_alice.patch(self.document_alice_url, {'upload_status': UploadStatus.FAILED.name})
        entity_ref_document_shipment_alice.attributes['upload_status'] = UploadStatus.FAILED.name
        AssertionHelper.HTTP_200(response, entity_ref_document_shipment_alice)
        assert isinstance(response.json()['data']['meta']['presigned_s3'], dict)

        mocker.patch('apps.documents.rpc.DocumentRPCClient.put_document_in_s3', return_value={'success': True})
        response = client_alice.patch(self.document_alice_url, {'upload_status': UploadStatus.COMPLETE.name})
        entity_ref_document_shipment_alice.attributes['description'] = UploadStatus.COMPLETE.name
        AssertionHelper.HTTP_200(response, entity_ref_document_shipment_alice)
        assert isinstance(response.json()['data']['meta']['presigned_s3'], str)
        assert isinstance(response.json()['data']['meta']['presigned_s3_thumbnail'], str)


class TestDocumentsList:
    @fixture(autouse=True)
    def set_up(self, shipment_alice, shipment_alice_two, mocked_engine_rpc):
        self.shipment_alice_url = reverse('shipment-documents-list',
                                          kwargs={'version': 'v1', 'shipment_pk': shipment_alice.id})
        self.shipment_alice_two_url = reverse('shipment-documents-list',
                                              kwargs={'version': 'v1', 'shipment_pk': shipment_alice_two.id})
        self.shipment_random_url = reverse('shipment-documents-list',
                                           kwargs={'version': 'v1', 'shipment_pk': random_id()})

    def test_requires_authentication(self, api_client):
        response = api_client.get(self.shipment_alice_url)
        AssertionHelper.HTTP_403(response)

    def test_wallet_permission_fail(self, client_bob, mock_non_wallet_owner_calls,
                                    nonsuccessful_wallet_owner_calls_assertions):
        response = client_bob.get(self.shipment_alice_url)
        AssertionHelper.HTTP_403(response)
        mock_non_wallet_owner_calls.assert_calls(nonsuccessful_wallet_owner_calls_assertions)

    def test_wallet_permission_success(self, client_bob, mock_successful_wallet_owner_calls,
                                       successful_wallet_owner_calls_assertions, entity_ref_document_shipment_alice):
        response = client_bob.get(self.shipment_alice_url)
        AssertionHelper.HTTP_200(response, entity_refs=[entity_ref_document_shipment_alice], count=1, is_list=True)
        mock_successful_wallet_owner_calls.assert_calls(successful_wallet_owner_calls_assertions)

    def test_org_access(self, client_alice, client_carol, entity_ref_document_shipment_alice):
        response = client_alice.get(self.shipment_alice_url)
        AssertionHelper.HTTP_200(response, entity_refs=[entity_ref_document_shipment_alice], count=1, is_list=True)

        response = client_carol.get(self.shipment_alice_url)
        AssertionHelper.HTTP_200(response, entity_refs=[entity_ref_document_shipment_alice], count=1, is_list=True)

    def test_per_shipment_return(self, client_alice, entity_ref_document_shipment_alice,
                                 entity_ref_document_shipment_alice_two, entity_ref_document_shipment_two_alice):
        response = client_alice.get(self.shipment_alice_url)
        AssertionHelper.HTTP_200(response, is_list=True,
                                 entity_refs=[entity_ref_document_shipment_alice,
                                              entity_ref_document_shipment_alice_two],
                                 count=2)

        response = client_alice.get(self.shipment_alice_two_url)
        AssertionHelper.HTTP_200(response, entity_refs=[entity_ref_document_shipment_two_alice], count=1, is_list=True)

    def test_filter(self, client_alice, entity_ref_document_shipment_alice, entity_ref_document_shipment_alice_two):
        response = client_alice.get(f'{self.shipment_alice_url}?file_type={entity_ref_document_shipment_alice.attributes["file_type"]}')
        AssertionHelper.HTTP_200(response, is_list=True,
                                 entity_refs=[entity_ref_document_shipment_alice],
                                 count=1)

        response = client_alice.get(f'{self.shipment_alice_url}?document_type={entity_ref_document_shipment_alice_two.attributes["document_type"]}')
        AssertionHelper.HTTP_200(response, is_list=True,
                                 entity_refs=[entity_ref_document_shipment_alice_two],
                                 count=1)

        response = client_alice.get(f'{self.shipment_alice_url}?upload_status={entity_ref_document_shipment_alice_two.attributes["upload_status"]}')
        AssertionHelper.HTTP_200(response, is_list=True,
                                 entity_refs=[entity_ref_document_shipment_alice_two],
                                 count=1)

    def test_search(self, client_alice, entity_ref_document_shipment_alice, entity_ref_document_shipment_alice_two,
                    document_shipment_alice, document_shipment_alice_two):
        document_shipment_alice.name = 'Document Name'
        document_shipment_alice.save()
        entity_ref_document_shipment_alice.attributes['name'] = 'Document Name'

        response = client_alice.get(f'{self.shipment_alice_url}?search=Name')
        AssertionHelper.HTTP_200(response, is_list=True,
                                 entity_refs=[entity_ref_document_shipment_alice],
                                 count=1)

        document_shipment_alice_two.description = 'Document Description'
        document_shipment_alice_two.save()
        entity_ref_document_shipment_alice_two.attributes['description'] = 'Document Description'
        response = client_alice.get(f'{self.shipment_alice_url}?search=Description')
        AssertionHelper.HTTP_200(response, is_list=True,
                                 entity_refs=[entity_ref_document_shipment_alice_two],
                                 count=1)

        response = client_alice.get(f'{self.shipment_alice_url}?search=Document')
        AssertionHelper.HTTP_200(response, is_list=True,
                                 entity_refs=[entity_ref_document_shipment_alice,
                                              entity_ref_document_shipment_alice_two],
                                 count=2)

    def test_ordering(self, client_alice, entity_ref_document_shipment_alice, entity_ref_document_shipment_alice_two):
        response = client_alice.get(f'{self.shipment_alice_url}?ordering=-created_at')
        AssertionHelper.HTTP_200(response, is_list=True,
                                 entity_refs=[entity_ref_document_shipment_alice_two, entity_ref_document_shipment_alice],
                                 check_ordering=True)

        response = client_alice.get(f'{self.shipment_alice_url}?ordering=-modified_at')
        AssertionHelper.HTTP_200(response, is_list=True,
                                 entity_refs=[entity_ref_document_shipment_alice_two, entity_ref_document_shipment_alice],
                                 check_ordering=True)
