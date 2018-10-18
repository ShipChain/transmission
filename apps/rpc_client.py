import json
import logging

import requests
from django.conf import settings
from rest_framework import status
from rest_framework.exceptions import APIException
from influxdb_metrics.loader import log_metric, TimingMetric

from apps.utils import DecimalEncoder

LOG = logging.getLogger('transmission')


class RPCError(APIException):
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    default_detail = 'Internal Service Error.'
    default_code = 'server_error'

    def __init__(self, detail, status_code=None, code=None):
        super(RPCError, self).__init__(detail, code)
        self.detail = detail
        LOG.error(f'RPC error with detail {detail}.')

        if status_code:
            self.status_code = status_code


class RPCClient(object):
    def __init__(self):
        self.url = settings.ENGINE_RPC_URL
        self.payload = {"jsonrpc": "2.0", "id": 0, "params": {}}
        self.session = requests.session()
        if settings.ENVIRONMENT in ('PROD', 'STAGE', 'DEV'):
            self.session.cert = ('/app/client-cert.crt', '/app/client-cert.key')
            self.session.verify = '/app/ca-bundle.crt'
        self.session.headers = {'content-type': 'application/json'}

    def call(self, method, args=None):
        LOG.debug(f'Calling RPCClient with method {method}.')
        log_metric('transmission.info', tags={'method': 'RPCClient.call', 'module': __name__})

        if args and not isinstance(args, object):
            raise RPCError("Invalid parameter type for Engine RPC call")

        self.payload['method'] = method
        self.payload['params'] = args or {}

        try:
            with TimingMetric('engine_rpc.call', tags={'method': method}) as timer:
                response_json = self.session.post(self.url, data=json.dumps(self.payload, cls=DecimalEncoder)).json()
                LOG.info('rpc_client(%s) duration: %.3f', method, timer.elapsed)

            if 'error' in response_json:
                log_metric('engine_rpc.error', tags={'method': method, 'code': response_json['error']['code'],
                                                     'module': __name__})
                LOG.error('rpc_client(%s) error: %s', method, response_json['error'])
                raise RPCError(response_json['error']['message'])

            response_json = response_json['result']

        except requests.exceptions.ConnectionError:
            # Don't return the true ConnectionError as it can contain internal URLs
            log_metric('engine_rpc.error', tags={'method': method, 'code': 'ConnectionError', 'module': __name__})
            raise RPCError("Service temporarily unavailable, try again later", status.HTTP_503_SERVICE_UNAVAILABLE,
                           'service_unavailable')

        except Exception as exception:
            log_metric('engine_rpc.error', tags={'method': method, 'code': 'Exception', 'module': __name__})
            raise RPCError(str(exception))

        return response_json

    def sign_transaction(self, wallet_id, transaction):
        LOG.debug(f'Signing transaction {transaction} with wallet_id {wallet_id}.')
        log_metric('transmission.info', tags={'method': 'RPCClient.sign_transaction', 'module': __name__})

        result = self.call('transaction.sign', {
            "signerWallet": wallet_id,
            "txUnsigned": transaction
        })

        if 'success' in result and result['success']:
            if 'transaction' in result:
                LOG.debug(f'Successful signing of transaction.')
                return result['transaction'], result['hash']

        log_metric('engine_rpc.error', tags={'method': 'RPCClient.sign_transaction', 'module': __name__})
        raise RPCError("Invalid response from Engine")

    def send_transaction(self, signed_transaction, callback_url):
        LOG.debug(f'Sending transaction {signed_transaction} with callback_url {callback_url}.')
        log_metric('transmission.info', tags={'method': 'RPCClient.send_transaction', 'module': __name__})

        result = self.call('transaction.send', {
            "callbackUrl": callback_url,
            "txSigned": signed_transaction
        })

        if 'success' in result and result['success']:
            if 'receipt' in result:
                LOG.debug(f'Successful sending of transaction.')
                return result['receipt']

        log_metric('engine_rpc.error', tags={'method': 'RPCClient.sign_transaction', 'module': __name__})
        raise RPCError("Invalid response from Engine")
