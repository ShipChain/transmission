import requests
from unittest import TestCase, mock

from shipchain_common.exceptions import RPCError
from shipchain_common.test_utils import mocked_rpc_response

from apps.documents.rpc import DocumentRPCClient
from apps.shipments.rpc import ShipmentRPCClient, Load110RPCClient

CARRIER_WALLET_ID = '3716ff65-3d03-4b65-9fd5-43d15380cff9'
SHIPPER_WALLET_ID = '48381c16-432b-493f-9f8b-54e88a84ec0a'
MODERATOR_WALLET_ID = '71baef8e-7067-493a-b533-51ed84c0124a'
STORAGE_CRED_ID = '77b72202-5bcd-49f4-9860-bc4ec4fee07b'
SHIPMENT_ID = '332dc6c8-b89e-449e-a802-0bfe760f83ff'
VAULT_ID = 'b715a8ff-9299-4c87-96de-a4b0a4a54509'
VAULT_HASH = '0xe9f28cb025350ef700158eed9a5b617a4f4185b31de06864fd02d67c839df583'


class TestShipmentRPCClient(TestCase):
    def test_vault_create(self):

        rpc_client = ShipmentRPCClient()

        # Error response from RPC Server should return server detail in exception
        with mock.patch.object(requests.Session, 'post') as mock_method:
            mock_method.return_value = mocked_rpc_response({
                "error": {
                    "code": 1337,
                    "message": "Error from RPC Server",
                },
            })
            try:
                rpc_client.create_vault(STORAGE_CRED_ID, SHIPPER_WALLET_ID, CARRIER_WALLET_ID)
                self.fail("Should have thrown RPC Error")
            except RPCError as rpc_error:
                self.assertEqual(rpc_error.status_code, 500)
                self.assertEqual(rpc_error.detail, 'Error from RPC Server')

            mock_method.return_value = mocked_rpc_response({
                "result": {
                    "code": 1337,
                    "message": "Invalid response from Engine",
                },
            })
            try:
                rpc_client.create_vault(STORAGE_CRED_ID, SHIPPER_WALLET_ID, CARRIER_WALLET_ID)
                self.fail("Should have thrown RPC Error")
            except RPCError as rpc_error:
                self.assertEqual(rpc_error.status_code, 500)
                self.assertEqual(rpc_error.detail, 'Invalid response from Engine')

            mock_method.return_value = mocked_rpc_response({
                "jsonrpc": "2.0",
                "result": {
                    "success": True,
                    "vault_id": CARRIER_WALLET_ID,
                    "vault_uri": SHIPPER_WALLET_ID
                },
                "id": 0
            })

            vault_id, vault_uri = rpc_client.create_vault(STORAGE_CRED_ID, SHIPPER_WALLET_ID, CARRIER_WALLET_ID)
            self.assertEqual(vault_id, CARRIER_WALLET_ID)
            self.assertEqual(vault_uri, SHIPPER_WALLET_ID)

    def test_add_shipment_data(self):

        rpc_client = ShipmentRPCClient()

        # Error response from RPC Server should return server detail in exception
        with mock.patch.object(requests.Session, 'post') as mock_method:
            mock_method.return_value = mocked_rpc_response({
                "error": {
                    "code": 1337,
                    "message": "Error from RPC Server",
                },
            })
            try:
                rpc_client.add_shipment_data(STORAGE_CRED_ID, SHIPPER_WALLET_ID, CARRIER_WALLET_ID, '{}')
                self.fail("Should have thrown RPC Error")
            except RPCError as rpc_error:
                self.assertEqual(rpc_error.status_code, 500)
                self.assertEqual(rpc_error.detail, 'Error from RPC Server')

            mock_method.return_value = mocked_rpc_response({
                "result": {
                    "code": 1337,
                    "message": "Error from RPC Server",
                },
            })
            try:
                rpc_client.add_shipment_data(STORAGE_CRED_ID, SHIPPER_WALLET_ID, CARRIER_WALLET_ID, '{}')
                self.fail("Should have thrown RPC Error")
            except RPCError as rpc_error:
                self.assertEqual(rpc_error.status_code, 500)
                self.assertEqual(rpc_error.detail, 'Invalid response from Engine')

            mock_method.return_value = mocked_rpc_response({
                "jsonrpc": "2.0",
                "result": {
                    "success": True,
                    "vault_signed": SHIPPER_WALLET_ID
                },
                "id": 0
            })

            vault_signed = rpc_client.add_shipment_data(STORAGE_CRED_ID, SHIPPER_WALLET_ID, CARRIER_WALLET_ID, '{}')
            self.assertEqual(vault_signed, SHIPPER_WALLET_ID)

    def test_add_tracking_data(self):

        rpc_client = ShipmentRPCClient()

        # Error response from RPC Server should return server detail in exception
        with mock.patch.object(requests.Session, 'post') as mock_method:
            mock_method.return_value = mocked_rpc_response({
                "error": {
                    "code": 1337,
                    "message": "Error from RPC Server",
                },
            })
            try:
                rpc_client.add_tracking_data(STORAGE_CRED_ID, SHIPPER_WALLET_ID, CARRIER_WALLET_ID, '{}')
                self.fail("Should have thrown RPC Error")
            except RPCError as rpc_error:
                self.assertEqual(rpc_error.status_code, 500)
                self.assertEqual(rpc_error.detail, 'Error from RPC Server')

            mock_method.return_value = mocked_rpc_response({
                "result": {
                    "code": 1337,
                    "message": "Error from RPC Server",
                },
            })
            try:
                rpc_client.add_tracking_data(STORAGE_CRED_ID, SHIPPER_WALLET_ID, CARRIER_WALLET_ID, '{}')
                self.fail("Should have thrown RPC Error")
            except RPCError as rpc_error:
                self.assertEqual(rpc_error.status_code, 500)
                self.assertEqual(rpc_error.detail, 'Invalid response from Engine')

            mock_method.return_value = mocked_rpc_response({
                "jsonrpc": "2.0",
                "result": {
                    "success": True,
                    "vault_signed": SHIPPER_WALLET_ID
                },
                "id": 0
            })

            vault_signed = rpc_client.add_tracking_data(STORAGE_CRED_ID, SHIPPER_WALLET_ID, CARRIER_WALLET_ID, '{}')
            self.assertEqual(vault_signed, SHIPPER_WALLET_ID)

    def test_get_tracking_data(self):

        rpc_client = ShipmentRPCClient()

        # Error response from RPC Server should return server detail in exception
        with mock.patch.object(requests.Session, 'post') as mock_method:
            mock_method.return_value = mocked_rpc_response({
                "error": {
                    "code": 1337,
                    "message": "Error from RPC Server",
                },
            })
            try:
                rpc_client.get_tracking_data(STORAGE_CRED_ID, SHIPPER_WALLET_ID, VAULT_ID)
                self.fail("Should have thrown RPC Error")
            except RPCError as rpc_error:
                self.assertEqual(rpc_error.status_code, 500)
                self.assertEqual(rpc_error.detail, 'Error from RPC Server')

            mock_method.return_value = mocked_rpc_response({
                "result": {
                    "code": 1337,
                    "message": "Error from RPC Server",
                },
            })
            try:
                rpc_client.get_tracking_data(STORAGE_CRED_ID, SHIPPER_WALLET_ID, VAULT_ID)
                self.fail("Should have thrown RPC Error")
            except RPCError as rpc_error:
                self.assertEqual(rpc_error.status_code, 500)
                self.assertEqual(rpc_error.detail, 'Invalid response from Engine')

            mock_method.return_value = mocked_rpc_response({
                "jsonrpc": "2.0",
                "result": {
                    "success": True,
                    "contents": {
                        "ayy": "lmao"
                    }
                },
                "id": 0
            })

            contents = rpc_client.get_tracking_data(STORAGE_CRED_ID, SHIPPER_WALLET_ID, VAULT_ID)
            self.assertEqual(contents, {
                        "ayy": "lmao"
                    })


class TestLoad110RPCClient(TestCase):

    def test_create_shipment_transaction(self):

        rpc_client = Load110RPCClient()

        # Error response from RPC Server should return server detail in exception
        with mock.patch.object(requests.Session, 'post') as mock_method:
            mock_method.return_value = mocked_rpc_response({
                "error": {
                    "code": 1337,
                    "message": "Error from RPC Server",
                },
            })
            try:
                rpc_client.create_shipment_transaction(STORAGE_CRED_ID, SHIPPER_WALLET_ID)
                # self.fail("Should have thrown RPC Error")
            except RPCError as rpc_error:
                self.assertEqual(rpc_error.status_code, 500)
                self.assertEqual(rpc_error.detail, 'Error from RPC Server')

            mock_method.return_value = mocked_rpc_response({
                "result": {
                    "code": 1337,
                    "message": "Error from RPC Server",
                },
            })
            try:
                rpc_client.create_shipment_transaction(STORAGE_CRED_ID, SHIPPER_WALLET_ID)
                # self.fail("Should have thrown RPC Error")
            except RPCError as rpc_error:
                self.assertEqual(rpc_error.status_code, 500)
                self.assertEqual(rpc_error.detail, 'Invalid response from Engine')

            mock_method.return_value = mocked_rpc_response({
                "jsonrpc": "2.0",
                "result": {
                    "success": True,
                    "transaction": SHIPPER_WALLET_ID,
                    "contractVersion": "v1"
                },
                "id": 0
            })

            contractVersion, transaction = rpc_client.create_shipment_transaction(STORAGE_CRED_ID, SHIPPER_WALLET_ID)
            self.assertEqual(contractVersion, "v1")
            self.assertEqual(transaction, SHIPPER_WALLET_ID)

    def test_set_vault_hash_tx(self):

        rpc_client = Load110RPCClient()

        # Error response from RPC Server should return server detail in exception
        with mock.patch.object(requests.Session, 'post') as mock_method:
            mock_method.return_value = mocked_rpc_response({
                "error": {
                    "code": 1337,
                    "message": "Error from RPC Server",
                },
            })
            try:
                rpc_client.set_vault_hash_tx(SHIPPER_WALLET_ID, SHIPMENT_ID, VAULT_HASH)
                self.fail("Should have thrown RPC Error")
            except RPCError as rpc_error:
                self.assertEqual(rpc_error.status_code, 500)
                self.assertEqual(rpc_error.detail, 'Error from RPC Server')

            mock_method.return_value = mocked_rpc_response({
                "jsonrpc": "2.0",
                "result": {
                    "success": True,
                    "transaction": VAULT_HASH
                },
                "id": 0
            })

            transaction = rpc_client.set_vault_hash_tx(STORAGE_CRED_ID, SHIPPER_WALLET_ID, CARRIER_WALLET_ID)
            self.assertEqual(transaction, VAULT_HASH)

    def test_set_vault_uri_tx(self):

        rpc_client = Load110RPCClient()

        # Error response from RPC Server should return server detail in exception
        with mock.patch.object(requests.Session, 'post') as mock_method:
            mock_method.return_value = mocked_rpc_response({
                "error": {
                    "code": 1337,
                    "message": "Error from RPC Server",
                },
            })
            try:
                rpc_client.set_vault_uri_tx(SHIPPER_WALLET_ID, SHIPMENT_ID, VAULT_ID)
                self.fail("Should have thrown RPC Error")
            except RPCError as rpc_error:
                self.assertEqual(rpc_error.status_code, 500)
                self.assertEqual(rpc_error.detail, 'Error from RPC Server')

            mock_method.return_value = mocked_rpc_response({
                "result": {
                    "code": 1337,
                    "message": "Invalid response from Engine",
                },
            })
            try:
                rpc_client.set_vault_uri_tx(SHIPPER_WALLET_ID, SHIPMENT_ID, VAULT_ID)
                self.fail("Should have thrown RPC Error")
            except RPCError as rpc_error:
                self.assertEqual(rpc_error.status_code, 500)
                self.assertEqual(rpc_error.detail, 'Invalid response from Engine')

            mock_method.return_value = mocked_rpc_response({
                "jsonrpc": "2.0",
                "result": {
                    "success": True,
                    "transaction": VAULT_HASH
                },
                "id": 0
            })

            transaction = rpc_client.set_vault_uri_tx(STORAGE_CRED_ID, SHIPPER_WALLET_ID, VAULT_ID)
            self.assertEqual(transaction, VAULT_HASH)

    def test_set_carrier_tx(self):

        rpc_client = Load110RPCClient()

        # Error response from RPC Server should return server detail in exception
        with mock.patch.object(requests.Session, 'post') as mock_method:
            mock_method.return_value = mocked_rpc_response({
                "error": {
                    "code": 1337,
                    "message": "Error from RPC Server",
                },
            })
            try:
                rpc_client.set_carrier_tx(SHIPPER_WALLET_ID, SHIPMENT_ID, CARRIER_WALLET_ID)
                self.fail("Should have thrown RPC Error")
            except RPCError as rpc_error:
                self.assertEqual(rpc_error.status_code, 500)
                self.assertEqual(rpc_error.detail, 'Error from RPC Server')

            mock_method.return_value = mocked_rpc_response({
                "result": {
                    "code": 1337,
                    "message": "Invalid response from Engine",
                },
            })
            try:
                rpc_client.set_carrier_tx(SHIPPER_WALLET_ID, SHIPMENT_ID, CARRIER_WALLET_ID)
                self.fail("Should have thrown RPC Error")
            except RPCError as rpc_error:
                self.assertEqual(rpc_error.status_code, 500)
                self.assertEqual(rpc_error.detail, 'Invalid response from Engine')

            mock_method.return_value = mocked_rpc_response({
                "jsonrpc": "2.0",
                "result": {
                    "success": True,
                    "transaction": VAULT_HASH
                },
                "id": 0
            })

            transaction = rpc_client.set_carrier_tx(SHIPPER_WALLET_ID, SHIPMENT_ID, CARRIER_WALLET_ID)
            self.assertEqual(transaction, VAULT_HASH)

    def test_set_moderator_tx(self):

        rpc_client = Load110RPCClient()

        # Error response from RPC Server should return server detail in exception
        with mock.patch.object(requests.Session, 'post') as mock_method:
            mock_method.return_value = mocked_rpc_response({
                "error": {
                    "code": 1337,
                    "message": "Error from RPC Server",
                },
            })
            try:
                rpc_client.set_moderator_tx(SHIPPER_WALLET_ID, SHIPMENT_ID, MODERATOR_WALLET_ID)
                self.fail("Should have thrown RPC Error")
            except RPCError as rpc_error:
                self.assertEqual(rpc_error.status_code, 500)
                self.assertEqual(rpc_error.detail, 'Error from RPC Server')

            mock_method.return_value = mocked_rpc_response({
                "result": {
                    "code": 1337,
                    "message": "Invalid response from Engine",
                },
            })
            try:
                rpc_client.set_moderator_tx(SHIPPER_WALLET_ID, SHIPMENT_ID, MODERATOR_WALLET_ID)
                self.fail("Should have thrown RPC Error")
            except RPCError as rpc_error:
                self.assertEqual(rpc_error.status_code, 500)
                self.assertEqual(rpc_error.detail, 'Invalid response from Engine')

            mock_method.return_value = mocked_rpc_response({
                "jsonrpc": "2.0",
                "result": {
                    "success": True,
                    "transaction": VAULT_HASH
                },
                "id": 0
            })

            transaction = rpc_client.set_moderator_tx(SHIPPER_WALLET_ID, SHIPMENT_ID, MODERATOR_WALLET_ID)
            self.assertEqual(transaction, VAULT_HASH)


class TestDocumentRPCClient(TestCase):
    def test_add_document_from_s3(self):
        rpc_client = DocumentRPCClient()

        with mock.patch.object(requests.Session, 'post') as mock_method:
            mock_method.return_value = mocked_rpc_response({
                "error": {
                    "code": 1337,
                    "message": "Error from RPC Server",
                },
            })
            try:
                rpc_client.add_document_from_s3(
                    'bucket',
                    's3_key',
                    SHIPPER_WALLET_ID,
                    STORAGE_CRED_ID,
                    VAULT_ID,
                    'Document Name'
                )
                self.fail("Should have thrown RPC Error")
            except RPCError as rpc_error:
                self.assertEqual(rpc_error.status_code, 500)
                self.assertEqual(rpc_error.detail, 'Error from RPC Server')

        with mock.patch.object(requests.Session, 'post') as mock_method:
            mock_method.return_value = mocked_rpc_response({
                "jsonrpc": "2.0",
                "result": {
                    "success": True,
                    "vault_signed": VAULT_HASH
                },
                "id": 0
            })

            vault_hash = rpc_client.add_document_from_s3(
                    bucket='bucket',
                    key='s3_key',
                    vault_wallet=SHIPPER_WALLET_ID,
                    storage_credentials=STORAGE_CRED_ID,
                    vault=VAULT_ID,
                    document_name='Document Name'
                )
            self.assertEqual(vault_hash, VAULT_HASH)

    def test_put_document_in_s3(self):
        rpc_client = DocumentRPCClient()

        with mock.patch.object(requests.Session, 'post') as mock_method:
            mock_method.return_value = mocked_rpc_response({
                "error": {
                    "code": 1337,
                    "message": "Error from RPC Server",
                },
            })
            rpc_response = rpc_client.put_document_in_s3(
                bucket='bucket',
                key='s3_key',
                vault_wallet=SHIPPER_WALLET_ID,
                storage_credentials=STORAGE_CRED_ID,
                vault=VAULT_ID,
                document_name='Document Name'
            )
            self.assertFalse(rpc_response)

        with mock.patch.object(requests.Session, 'post') as mock_method:
            mock_method.return_value = mocked_rpc_response({
                "jsonrpc": "2.0",
                "result": {
                    "success": True,
                },
                "id": 0
            })
            rpc_response = rpc_client.put_document_in_s3(
                bucket='bucket',
                key='s3_key',
                vault_wallet=SHIPPER_WALLET_ID,
                storage_credentials=STORAGE_CRED_ID,
                vault=VAULT_ID,
                document_name='Document Name'
            )

            self.assertTrue(rpc_response)
