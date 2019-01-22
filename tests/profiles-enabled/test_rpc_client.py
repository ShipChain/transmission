from unittest import TestCase, mock

from django.conf import settings

from apps.rpc_client import RPCClient, RPCError, requests
from tests.utils import mocked_rpc_response


class RPCClientTest(TestCase):

    def test_rpc_init(self):

        rpc_client = RPCClient()
        self.assertEqual(rpc_client.url, settings.ENGINE_RPC_URL)

        self.assertIn('jsonrpc', rpc_client.payload)
        self.assertIn('id', rpc_client.payload)
        self.assertIn('params', rpc_client.payload)
        self.assertEqual(rpc_client.url, 'http://INTENTIONALLY_DISCONNECTED:9999')
        self.assertEqual(rpc_client.payload['id'], 0)
        self.assertEqual(rpc_client.payload['params'], {})

    def test_call(self):

        rpc_client = RPCClient()

        # Call without the backend should return the 503 RPCError
        try:
            rpc_client.call('test_method')
            self.fail("Should have thrown RPC Error")
        except RPCError as rpc_error:
            self.assertEqual(rpc_error.status_code, 503)
            self.assertEqual(rpc_error.detail, 'Service temporarily unavailable, try again later')

        # Error response from RPC Server should return server detail in exception
        with mock.patch.object(requests.Session, 'post') as mock_method:
            mock_method.return_value = mocked_rpc_response({
                "error": {
                    "code": 1337,
                    "message": "Error from RPC Server",
                },
            })
            try:
                rpc_client.call('test_method')
                self.fail("Should have thrown RPC Error")
            except RPCError as rpc_error:
                self.assertEqual(rpc_error.status_code, 500)
                self.assertEqual(rpc_error.detail, 'Error from RPC Server')

        # Response object from server should be returned on success
        with mock.patch.object(requests.Session, 'post') as mock_method:
            mock_method.return_value = mocked_rpc_response({
                "jsonrpc": "2.0",
                "result": {
                    "success": True,
                    "test_object": {
                        "id": "d5563423-f040-4e0d-8d87-5e941c748d91",
                    }
                },
                "id": 0
            })

            response_json = rpc_client.call('test_method')
            self.assertEqual(response_json['test_object'], {
                "id": "d5563423-f040-4e0d-8d87-5e941c748d91",
            })
