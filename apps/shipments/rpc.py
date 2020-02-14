import logging

from abc import abstractmethod
from django.conf import settings
from django.core.cache import cache
from influxdb_metrics.loader import log_metric
from shipchain_common.exceptions import RPCError
from shipchain_common.rpc import RPCClient

LOG = logging.getLogger('transmission')


class ShipmentRPCClient(RPCClient):
    def create_vault(self, storage_credentials_id, shipper_wallet_id, carrier_wallet_id):
        LOG.debug(f'Creating vault with storage_credentials_id {storage_credentials_id},'
                  f'shipper_wallet_id {shipper_wallet_id}, and carrier_wallet_id {carrier_wallet_id}.')
        log_metric('transmission.info', tags={'method': 'shipment_rpcclient.create_vault', 'module': __name__})

        result = self.call('vault.create', {
            "storageCredentials": storage_credentials_id,
            "shipperWallet": shipper_wallet_id,
            "carrierWallet": carrier_wallet_id
        })

        if 'success' in result and result['success']:
            if 'vault_id' in result:
                LOG.debug(f'Succesful creation of vault with id {result["vault_id"]}.')

                return result['vault_id'], result['vault_uri']

        LOG.error('Invalid creation of vault.')
        log_metric('transmission.error', tags={'method': 'shipment_rpcclient.create_vault', 'module': __name__,
                                               'code': 'RPCError'})
        raise RPCError("Invalid response from Engine")

    def add_shipment_data(self, storage_credentials_id, wallet_id, vault_id, shipment_data):
        with cache.lock(vault_id, timeout=settings.VAULT_TIMEOUT):
            LOG.debug(f'Adding shipment data with storage_credentials_id {storage_credentials_id},'
                      f'wallet_id {wallet_id}, and vault_id {vault_id}.')
            log_metric('transmission.info', tags={'method': 'shipment_rpcclient.add_shipment_data',
                                                  'module': __name__})

            result = self.call('vault.add_shipment', {
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
        with cache.lock(vault_id, timeout=settings.VAULT_TIMEOUT):
            LOG.debug(f'Adding tracking data with storage_credentials_id {storage_credentials_id},'
                      f'wallet_id {wallet_id}, and vault_id {vault_id}.')
            log_metric('transmission.info', tags={'method': 'shipment_rpcclient.add_tracking_data',
                                                  'module': __name__})

            result = self.call('vault.add_tracking', {
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

    def create_shipment_transaction(self, shipper_wallet_id, shipment_id):
        LOG.debug(
            f'Creating shipment transaction with '
            f'shipper_wallet_id {shipper_wallet_id}, and shipment_id {shipment_id}.')
        log_metric('transmission.info', tags={'method': 'shipment_rpcclient.create_shipment_transaction',
                                              'module': __name__})

        result = self.call('load.create_shipment_tx', {
            "senderWallet": shipper_wallet_id,
            "shipmentUuid": shipment_id
        })

        if 'success' in result and result['success']:
            if 'transaction' in result and 'contractVersion' in result:
                LOG.debug('Successful creation of shipment transaction.')
                return result['contractVersion'], result['transaction']

        log_metric('transmission.error', tags={'method': 'shipment_rpcclient.create_shipment_transaction',
                                               'module': __name__, 'code': 'RPCError'})
        LOG.error('Invalid creation of shipment data.')
        raise RPCError("Invalid response from Engine")

    def add_telemetry_data(self, storage_credentials_id, wallet_id, vault_id, telemetry_data):
        with cache.lock(vault_id, timeout=settings.VAULT_TIMEOUT):
            LOG.debug(f'Adding telemetry data with storage_credentials_id {storage_credentials_id},'
                      f'wallet_id {wallet_id}, and vault_id {vault_id}.')
            log_metric('transmission.info', tags={'method': 'shipment_rpcclient.add_telemetry_data',
                                                  'module': __name__})

            result = self.call('vault.add_telemetry', {
                "storageCredentials": storage_credentials_id,
                "vaultWallet": wallet_id,
                "vault": vault_id,
                "payload": telemetry_data
            })

            if 'success' in result and result['success']:
                LOG.debug('Successful addition of telemetry data.')
                return result['vault_signed']

            log_metric('transmission.error', tags={'method': 'shipment_rpcclient.add_telemetry_data',
                                                   'module': __name__, 'code': 'RPCError'})
            LOG.error('Invalid addition of telemetry data.')
            raise RPCError("Invalid response from Engine")

    def get_tracking_data(self, storage_credentials_id, wallet_id, vault_id):
        LOG.debug(f'Retrieving of tracking data with storage_credentials_id {storage_credentials_id},'
                  f'wallet_id {wallet_id}, and vault_id {vault_id}.')
        log_metric('transmission.info', tags={'method': 'shipment_rpcclient.get_tracking_data',
                                              'module': __name__})

        result = self.call('vault.get_tracking', {
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

    def get_telemetry_data(self, storage_credentials_id, wallet_id, vault_id):
        LOG.debug(f'Retrieving of telemetry data with storage_credentials_id {storage_credentials_id},'
                  f'wallet_id {wallet_id}, and vault_id {vault_id}.')
        log_metric('transmission.info', tags={'method': 'shipment_rpcclient.get_telemetry_data',
                                              'module': __name__})

        result = self.call('vault.get_telemetry', {
            "storageCredentials": storage_credentials_id,
            "vaultWallet": wallet_id,
            "vault": vault_id
        })

        if 'success' in result and result['success']:
            if 'contents' in result:
                LOG.debug('Successful retrieval of telemetry data.')
                return result['contents']

        log_metric('transmission.error', tags={'method': 'shipment_rpcclient.get_telemetry_data',
                                               'module': __name__, 'code': 'RPCError'})
        LOG.error('Invalid retrieval of telemetry data.')
        raise RPCError("Invalid response from Engine")

    @abstractmethod
    def set_vault_hash_tx(self, wallet_id, current_shipment_id, vault_hash):
        pass


class Load110RPCClient(ShipmentRPCClient):

    def set_vault_hash_tx(self, wallet_id, current_shipment_id, vault_hash):
        LOG.debug(f'Updating vault hash transaction with current_shipment_id {current_shipment_id},'
                  f'vault_hash {vault_hash}, and wallet_id {wallet_id}.')
        log_metric('transmission.info', tags={'method': 'shipment_rpcclient.set_vault_hash_tx',
                                              'module': __name__})

        result = self.call('load.1.1.0.set_vault_hash_tx', {
            "senderWallet": wallet_id,
            "shipmentUuid": current_shipment_id,
            "hash": vault_hash
        })

        if 'success' in result and result['success']:
            if 'transaction' in result and result['transaction']:
                LOG.debug('Successful update of vault hash transaction.')
                return result['transaction']

        log_metric('transmission.error', tags={'method': 'shipment_rpcclient.set_vault_hash_tx',
                                               'module': __name__, 'code': 'RPCError'})
        LOG.error('Invalid update of vault hash transaction.')
        raise RPCError("Invalid response from Engine")

    def set_vault_uri_tx(self, wallet_id, current_shipment_id, vault_uri):
        LOG.debug(f'Updating vault URI for current_shipment_id {current_shipment_id},'
                  f'vault_uri {vault_uri}, and wallet_id {wallet_id}.')
        log_metric('transmission.info', tags={'method': 'shipment_rpcclient.set_vault_uri_tx',
                                              'module': __name__})

        result = self.call('load.1.1.0.set_vault_uri_tx', {
            "senderWallet": wallet_id,
            "shipmentUuid": current_shipment_id,
            "uri": vault_uri
        })

        if 'success' in result and result['success']:
            if 'transaction' in result and result['transaction']:
                LOG.debug('Successful update of vault uri transaction.')
                return result['transaction']

        log_metric('transmission.error', tags={'method': 'shipment_rpcclient.set_vault_uri_tx',
                                               'module': __name__, 'code': 'RPCError'})
        LOG.error('Invalid update of vault uri transaction.')
        raise RPCError("Invalid response from Engine")

    def set_carrier_tx(self, wallet_id, current_shipment_id, carrier_wallet):
        LOG.debug(f'Updating carrier for current_shipment_id {current_shipment_id},'
                  f'carrier {carrier_wallet}, and wallet_id {wallet_id}.')
        log_metric('transmission.info', tags={'method': 'shipment_rpcclient.set_carrier_tx',
                                              'module': __name__})

        result = self.call('load.1.1.0.set_carrier_tx', {
            "senderWallet": wallet_id,
            "shipmentUuid": current_shipment_id,
            "carrierWallet": carrier_wallet
        })

        if 'success' in result and result['success']:
            if 'transaction' in result and result['transaction']:
                LOG.debug('Successful update of carrier wallet transaction.')
                return result['transaction']

        log_metric('transmission.error', tags={'method': 'shipment_rpcclient.set_carrier_tx',
                                               'module': __name__, 'code': 'RPCError'})
        LOG.error('Invalid update of carrier wallet transaction.')
        raise RPCError("Invalid response from Engine")

    def set_moderator_tx(self, wallet_id, current_shipment_id, moderator_wallet):
        LOG.debug(f'Updating moderator for current_shipment_id {current_shipment_id},'
                  f'carrier {moderator_wallet}, and wallet_id {wallet_id}.')
        log_metric('transmission.info', tags={'method': 'shipment_rpcclient.set_moderator_tx',
                                              'module': __name__})

        result = self.call('load.1.1.0.set_moderator_tx', {
            "senderWallet": wallet_id,
            "shipmentUuid": current_shipment_id,
            "moderatorWallet": moderator_wallet
        })

        if 'success' in result and result['success']:
            if 'transaction' in result and result['transaction']:
                LOG.debug('Successful update of moderator wallet transaction.')
                return result['transaction']

        log_metric('transmission.error', tags={'method': 'shipment_rpcclient.set_moderator_tx',
                                               'module': __name__, 'code': 'RPCError'})
        LOG.error('Invalid update of moderator wallet transaction.')
        raise RPCError("Invalid response from Engine")


class RPCClientFactory:
    clients = {}

    @staticmethod
    def get_client(contract_version=None):
        if contract_version not in RPCClientFactory.clients:
            if not contract_version:
                RPCClientFactory.clients[contract_version] = Load110RPCClient()  # Default version
            elif contract_version == '1.1.0':
                RPCClientFactory.clients[contract_version] = Load110RPCClient()
            else:
                raise RPCError(f'No such RPCClient for LOAD {contract_version}')

        return RPCClientFactory.clients[contract_version]
