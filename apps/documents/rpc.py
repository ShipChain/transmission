"""
Copyright 2018 ShipChain, Inc.

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""

import logging

from influxdb_metrics.loader import log_metric

from apps.rpc_client import RPCClient, RPCError

LOG = logging.getLogger('transmission')


class DocumentRPCClient(RPCClient):
    # pylint:disable=too-many-arguments
    def add_document_from_s3(self, bucket, key, vault_wallet, storage_credentials, vault, document_name):
        LOG.debug(f'Telling Engine to fetch doc {document_name} from bucket {bucket} at {key} and put in vault {vault}')
        log_metric('transmission.info', tags={'method': 'document_rpcclient.add_document_from_s3',
                                              'module': __name__})

        result = self.call('vault.add_document_from_s3', {
            "bucket": bucket,
            "key": key,
            "vaultWallet": vault_wallet,
            "storageCredentials": storage_credentials,
            "vault": vault,
            "documentName": document_name,
        })

        if 'success' in result and result['success']:
            if 'vault_signed' in result:
                return

        log_metric('transmission.error', tags={'method': 'document_rpcclient.add_document_from_s3', 'code': 'RPCError',
                                               'module': __name__})
        raise RPCError("Invalid response from Engine")

    def put_document_in_s3(self, bucket, key, vault_wallet, storage_credentials, vault, document_name):
        LOG.debug(f'Telling Engine to put doc: {document_name} from vault: {vault} with {key} to s3 bucket: {bucket}')
        log_metric('transmission.info', tags={'method': 'document_rpcclient.put_document_in_s3',
                                              'module': __name__})

        result = self.call('vault.put_document_in_s3', {
            "bucket": bucket,
            "key": key,
            "vaultWallet": vault_wallet,
            "storageCredentials": storage_credentials,
            "vault": vault,
            "documentName": document_name,
        })

        if result.get('success', None):
            return

        log_metric('transmission.error', tags={'method': 'document_rpcclient.put_document_in_s3', 'code': 'RPCError',
                                               'module': __name__})
        raise RPCError("Invalid response from Engine")
