import json
from unittest import mock

import requests
from django.urls import reverse
from shipchain_common.test_utils import AssertionHelper, mocked_rpc_response
from shipchain_common.utils import random_id

from apps.utils import UploadStatus


class TestS3EventNotification:
    url = reverse('document-events', kwargs={'version': 'v1'})

    # S3 Lambda PutObject event: https://docs.aws.amazon.com/lambda/latest/dg/eventsources.html#eventsources-s3-put
    s3_event = {"Records": [{"s3": {
        "bucket": {"name": "document-management-s3-local"},
        "object": {"key": "sc_uuid/wallet_uuid/vault_uuid/document_uuid.ext"}
    }}]}

    def test_requires_internal(self, api_client):
        response = api_client.post(self.url, json.dumps(self.s3_event))
        AssertionHelper.HTTP_403(response)

    def test_requires_document(self, api_client, document_shipment_alice, mock_s3_buckets):
        self.s3_event["Records"][0]["s3"]["object"]["key"] = f"{random_id()}/{random_id()}/{random_id()}/{random_id()}.png"
        response = api_client.post(self.url, json.dumps(self.s3_event), content_type="application/json",
                                   X_NGINX_SOURCE='internal', X_SSL_CLIENT_VERIFY='SUCCESS',
                                   X_SSL_CLIENT_DN='/CN=document-management-s3-hook.test-internal')
        AssertionHelper.HTTP_400(response, error='Document not found with ID')

        with mock.patch.object(requests.Session, 'post') as mock_method:
            mock_method.return_value = mocked_rpc_response({
                "jsonrpc": "2.0",
                "result": {
                    "success": False
                },
                "id": 0
            })
            self.s3_event["Records"][0]["s3"]["object"]["key"] = f"{random_id()}/{random_id()}/{random_id()}/{document_shipment_alice.id}.png"
            response = api_client.post(self.url, json.dumps(self.s3_event), content_type="application/json",
                                       X_NGINX_SOURCE='internal', X_SSL_CLIENT_VERIFY='SUCCESS',
                                       X_SSL_CLIENT_DN='/CN=document-management-s3-hook.test-internal')
            AssertionHelper.HTTP_500(response, error='Invalid response from Engine')

            mock_method.return_value = mocked_rpc_response({
                "jsonrpc": "2.0",
                "result": {
                    "success": True,
                    "vault_signed": {
                        'hash': 'VAULT_HASH'
                    }
                },
                "id": 0
            })
            self.s3_event["Records"][0]["s3"]["object"]["key"] = f"{random_id()}/{random_id()}/{random_id()}/{document_shipment_alice.id}.png"
            response = api_client.post(self.url, json.dumps(self.s3_event), content_type="application/json",
                                       X_NGINX_SOURCE='internal', X_SSL_CLIENT_VERIFY='SUCCESS',
                                       X_SSL_CLIENT_DN='/CN=document-management-s3-hook.test-internal')
            AssertionHelper.HTTP_204(response)
            document_shipment_alice.refresh_from_db()
            assert document_shipment_alice.upload_status == UploadStatus.COMPLETE

    def test_idempotent(self, api_client, document_shipment_alice):
        document_shipment_alice.upload_status = UploadStatus.COMPLETE
        document_shipment_alice.save()

        history_count = document_shipment_alice.history.count()
        self.s3_event["Records"][0]["s3"]["object"]["key"] = f"{random_id()}/{random_id()}/{random_id()}/{document_shipment_alice.id}.png"
        response = api_client.post(self.url, json.dumps(self.s3_event), content_type="application/json",
                                   X_NGINX_SOURCE='internal', X_SSL_CLIENT_VERIFY='SUCCESS',
                                   X_SSL_CLIENT_DN='/CN=document-management-s3-hook.test-internal')
        AssertionHelper.HTTP_204(response)
        document_shipment_alice.refresh_from_db()
        assert document_shipment_alice.upload_status == UploadStatus.COMPLETE
        assert document_shipment_alice.history.count() == history_count

