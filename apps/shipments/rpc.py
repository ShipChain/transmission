from apps.rpc_client import RPCClient, RPCError


class ShipmentRPCClient(RPCClient):
    def create_vault(self, storage_credentials_id, shipper_wallet_id, carrier_wallet_id):

        result = self.call('load.create_vault', {
            "storageCredentials": storage_credentials_id,
            "shipperWallet": shipper_wallet_id,
            "carrierWallet": carrier_wallet_id
        })

        if 'success' in result and result['success']:
            if 'vault_id' in result:
                return result['vault_id']
        raise RPCError("Invalid response from Engine")

    def add_shipment_data(self, storage_credentials_id, wallet_id, vault_id, shipment_data):

        result = self.call('load.add_shipment_data', {
            "storageCredentials": storage_credentials_id,
            "vaultWallet": wallet_id,
            "vault": vault_id,
            "shipment": shipment_data
        })

        if 'success' in result and result['success']:
            return result['vault_signed']
        raise RPCError("Invalid response from Engine")

    def create_shipment_transaction(self, shipper_wallet_id, carrier_wallet_id,  # pylint: disable=too-many-arguments
                                    valid_until, funding_type, shipment_amount):

        result = self.call('load.create_shipment_transaction', {
            "shipperWallet": shipper_wallet_id,
            "carrierWallet": carrier_wallet_id,
            "validUntil": valid_until,
            "fundingType": funding_type,
            "shipmentAmount": shipment_amount
        })

        if 'success' in result and result['success']:
            if 'transaction' in result and 'contractVersion' in result:
                return result['contractVersion'], result['transaction']

        raise RPCError("Invalid response from Engine")

    def get_tracking_data(self, storage_credentials_id, wallet_id, vault_id):

        result = self.call('load.get_tracking_data', {
            "storageCredentials": storage_credentials_id,
            "vaultWallet": wallet_id,
            "vault": vault_id
        })

        if 'success' in result and result['success']:
            if 'contents' in result:
                return result['contents']

        raise RPCError("Invalid response from Engine")

    def update_vault_hash_transaction(self, wallet_id, current_shipment_id, url, vault_hash):
        result = self.call('load.update_vault_hash_transaction', {
            "shipperWallet": wallet_id,
            "shipmentId": current_shipment_id,
            "url": url,
            "hash": vault_hash
        })

        if 'success' in result and result['success']:
            if 'transaction' in result:
                return result['transaction']

        raise RPCError("Invalid response from Engine")
