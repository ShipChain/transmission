import json
import logging
import requests
from rest_framework import status

from rest_framework.exceptions import APIException

from django.conf import settings

from influxdb_metrics.loader import log_metric, TimingMetric

LOG = logging.getLogger('transmission')


class RPCError(APIException):
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    default_detail = 'Internal Service Error.'
    default_code = 'server_error'

    def __init__(self, detail, status_code=None, code=None):
        super(RPCError, self).__init__(detail, code)
        self.detail = detail

        if status_code:
            self.status_code = status_code


class RPCClient(object):
    def __init__(self):
        self.url = settings.ENGINE_RPC_URL
        self.headers = {'content-type': 'application/json'}
        self.payload = {"jsonrpc": "2.0", "id": 0, "params": {}}

    def call(self, method, args=None):

        if args and not isinstance(args, object):
            raise RPCError("Invalid parameter type for Engine RPC call")

        self.payload['method'] = method
        self.payload['params'] = args or {}

        try:
            with TimingMetric('engine_rpc.call', tags={'method': method}) as timer:
                response_json = requests.post(self.url, data=json.dumps(self.payload), headers=self.headers).json()
                LOG.info('rpc_client(%s) duration: %.3f', method, timer.elapsed)

            if 'error' in response_json:
                log_metric('engine_rpc.error', tags={'method': method, 'code': response_json['error']['code']})
                LOG.error('rpc_client(%s) error: %s', method, response_json['error'])
                raise RPCError(response_json['error']['message'])

            response_json = response_json['result']

        except requests.exceptions.ConnectionError:
            # Don't return the true ConnectionError as it can contain internal URLs
            log_metric('engine_rpc.error', tags={'method': method, 'code': 'ConnectionError'})
            raise RPCError("Service temporarily unavailable, try again later", status.HTTP_503_SERVICE_UNAVAILABLE,
                           'service_unavailable')

        except Exception as exception:
            log_metric('engine_rpc.error', tags={'method': method, 'code': 'Exception'})
            raise RPCError(str(exception))

        return response_json

    def sign_transaction(self, wallet_id, transaction):

        result = self.call('transaction.sign', {
            "signerWallet": wallet_id,
            "txUnsigned": transaction
        })

        if 'success' in result and result['success']:
            if 'transaction' in result:
                return result['transaction'], result['hash']
        raise RPCError("Invalid response from Engine")

    def send_transaction(self, signed_transaction, callback_url):

        result = self.call('transaction.send', {
            "callbackUrl": callback_url,
            "txSigned": signed_transaction
        })

        if 'success' in result and result['success']:
            if 'receipt' in result:
                return result['receipt']
        raise RPCError("Invalid response from Engine")
