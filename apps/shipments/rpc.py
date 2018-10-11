import logging

from django.core.cache import cache
from influxdb_metrics.loader import log_metric

from apps.rpc_client import RPCClient, RPCError

LOG = logging.getLogger('transmission')


class ShipmentRPCClient(RPCClient):
    def create_vault(self, storage_credentials_id, shipper_wallet_id, carrier_wallet_id):
        LOG.debug(f'Creating vault with storage_credentials_id {storage_credentials_id},'
                  f'shipper_wallet_id {shipper_wallet_id}, and carrier_wallet_id {carrier_wallet_id}.')
        log_metric('transmission.info', tags={'method': 'shipment_rpcclient.create_vault', 'module': __name__})

        result = self.call('load.create_vault', {
            "storageCredentials": storage_credentials_id,
            "shipperWallet": shipper_wallet_id,
            "carrierWallet": carrier_wallet_id
        })

        if 'success' in result and result['success']:
            if 'vault_id' in result:
                LOG.debug(f'Succesful creation of vault with id {result["vault_id"]}.')

                return result['vault_id']

        LOG.error('Invalid creation of vault.')
        log_metric('transmission.error', tags={'method': 'shipment_rpcclient.create_vault', 'module': __name__,
                                               'code': 'RPCError'})
        raise RPCError("Invalid response from Engine")

    def add_shipment_data(self, storage_credentials_id, wallet_id, vault_id, shipment_data):
        with cache.lock(vault_id):
            LOG.debug(f'Adding shipment data with storage_credentials_id {storage_credentials_id},'
                      f'wallet_id {wallet_id}, and vault_id {vault_id}.')
            log_metric('transmission.info', tags={'method': 'shipment_rpcclient.add_shipment_data',
                                                  'module': __name__})

            result = self.call('load.add_shipment_data', {
                "storageCredentials": storage_credentials_id,
                "vaultWallet": wallet_id,
                "vault": vault_id,
                "shipment": shipment_data
            })

            if 'success' in result and result['success']:
                LOG.debug('Successful addition of shipment data.')
                return result['vault_signed']

            log_metric('transmission.error', tags={'method': 'shipment_rpcclient.add_shipment_data',
                                                   'module': __name__, 'code': 'RPCError'})
            LOG.error('Invalid addition of shipment data.')
            raise RPCError("Invalid response from Engine")

    def add_tracking_data(self, storage_credentials_id, wallet_id, vault_id, tracking_data):
        with cache.lock(vault_id):
            LOG.debug(f'Adding tracking data with storage_credentials_id {storage_credentials_id},'
                      f'wallet_id {wallet_id}, and vault_id {vault_id}.')
            log_metric('transmission.info', tags={'method': 'shipment_rpcclient.add_tracking_data',
                                                  'module': __name__})

            result = self.call('load.add_tracking_data', {
                "storageCredentials": storage_credentials_id,
                "vaultWallet": wallet_id,
                "vault": vault_id,
                "payload": tracking_data
            })

            if 'success' in result and result['success']:
                LOG.debug('Successful addition of tracking data.')
                return result['vault_signed']

            log_metric('transmission.error', tags={'method': 'shipment_rpcclient.add_tracking_data',
                                                   'module': __name__, 'code': 'RPCError'})
            LOG.error('Invalid addition of tracking data.')
            raise RPCError("Invalid response from Engine")

    def create_shipment_transaction(self, shipper_wallet_id, carrier_wallet_id,  # pylint: disable=too-many-arguments
                                    valid_until, funding_type, shipment_amount):
        LOG.debug(f'Creating shipment transaction with funding_type {funding_type}, shipment_amount {shipment_amount},'
                  f'shipper_wallet_id {shipper_wallet_id}, and carrier_wallet_id {carrier_wallet_id}.')
        log_metric('transmission.info', tags={'method': 'shipment_rpcclient.create_shipment_transaction',
                                              'module': __name__})

        result = self.call('load.create_shipment_transaction', {
            "shipperWallet": shipper_wallet_id,
            "carrierWallet": carrier_wallet_id,
            "validUntil": valid_until,
            "fundingType": funding_type,
            "shipmentAmount": shipment_amount
        })

        if 'success' in result and result['success']:
            if 'transaction' in result and 'contractVersion' in result:
                LOG.debug('Successful creation of shipment transaction.')
                return result['contractVersion'], result['transaction']

        log_metric('transmission.error', tags={'method': 'shipment_rpcclient.create_shipment_transaction',
                                               'module': __name__, 'code': 'RPCError'})
        LOG.error('Invalid creation of shipment data.')
        raise RPCError("Invalid response from Engine")

    def get_tracking_data(self, storage_credentials_id, wallet_id, vault_id):
        LOG.debug(f'Retrieving of tracking data with storage_credentials_id {storage_credentials_id},'
                  f'wallet_id {wallet_id}, and vault_id {vault_id}.')
        log_metric('transmission.info', tags={'method': 'shipment_rpcclient.get_tracking_data',
                                              'module': __name__})

        result = self.call('load.get_tracking_data', {
            "storageCredentials": storage_credentials_id,
            "vaultWallet": wallet_id,
            "vault": vault_id
        })

        if 'success' in result and result['success']:
            if 'contents' in result:
                LOG.debug('Successful retrieval of tracking data.')
                return result['contents']

        log_metric('transmission.error', tags={'method': 'shipment_rpcclient.get_tracking_data',
                                               'module': __name__, 'code': 'RPCError'})
        LOG.error('Invalid retrieval of tracking data.')
        raise RPCError("Invalid response from Engine")

    def update_vault_hash_transaction(self, wallet_id, current_shipment_id, url, vault_hash):
        LOG.debug(f'Updating vault hash transaction with current_shipment_id {current_shipment_id},'
                  f'vault_hash {vault_hash}, and wallet_id {wallet_id}.')
        log_metric('transmission.info', tags={'method': 'shipment_rpcclient.update_vault_hash_transaction',
                                              'module': __name__})

        result = self.call('load.update_vault_hash_transaction', {
            "shipperWallet": wallet_id,
            "shipmentId": current_shipment_id,
            "url": url,
            "hash": vault_hash
        })

        if 'success' in result and result['success']:
            if 'transaction' in result:
                LOG.debug('Successful update of vault hash transaction.')
                return result['transaction']

        log_metric('transmission.error', tags={'method': 'shipment_rpcclient.update_vault_hash_transaction',
                                               'module': __name__, 'code': 'RPCError'})
        LOG.error('Invalid update of vault hash transaction.')
        raise RPCError("Invalid response from Engine")
