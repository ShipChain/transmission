from rest_framework_json_api import serializers

from apps.eth.fields import HASH_REGEX
from apps.eth.models import Event, EthAction, Transaction, TransactionReceipt
from apps.jobs.serializers import AsyncJobSerializer
from apps.shipments.serializers import FKShipmentSerializer


class TransactionSerializer(serializers.ModelSerializer):
    """
    "hash": "0x9fc76417374aa880d4449a1f7f31ec597f00b1f6f3dd2d66f4c9c6c445836d8b",
    "nonce": 2,
    "blockHash": "0xef95f2f1ed3ca60b048b4bf67cde2195961e0bba6f70bcbea9a2c4e133e34b46",
    "blockNumber": 3,
    "transactionIndex": 0,
    "from": "0xa94f5374fce5edbc8e2a8697c15331677e6ebf0b",
    "to": "0x6295ee1b4f6dd65047762f924ecd367c17eabf8f",
    "value": '123450000000000000',
    "gas": 314159,
    "gasPrice": '2000000000000',
    "input": "0x57cb2fc4"
    """
    hash = serializers.RegexField(HASH_REGEX.regex, source='eth_action_id', max_length=66)

    class Meta:
        model = Transaction
        exclude = ('eth_action',)


class TransactionReceiptSerializer(serializers.ModelSerializer):
    """
    "blockHash": "0x38823cb26b528867c8dbea4146292908f55e1ee7f293685db1df0851d1b93b24",
    "blockNumber": 14,
    "contractAddress": null,
    "cumulativeGasUsed": 270710,
    "from": "0x13b1eebb31a1aa2ecaa2ad9e7455df2f717f2143",
    "gasUsed": 270710,
    "logs": [
        {
            "address": "0x25Ff5dc79A7c4e34254ff0f4a19d69E491201DD3",
            "topics": [
                "0x485397dbe4d658daac8124e3080f66a255b9207fa36d7e757ba4d52fe6c21f54"
            ],
            "data": "0x0000000000000000000000000000...00000000000000000002",
            "blockNumber": 14,
            "transactionHash": "0x7ff1a69326d64507a306a836128aa67503972cb38e22fa6db217ec553c560d76",
            "transactionIndex": 0,
            "blockHash": "0x38823cb26b528867c8dbea4146292908f55e1ee7f293685db1df0851d1b93b24",
            "logIndex": 0,
            "removed": false,
            "id": "log_025179b7"
        }
    ],
    "logsBloom": "0x0000000000000000000000000000000...00000000000000000000",
    "status": true,
    "to": "0x25ff5dc79a7c4e34254ff0f4a19d69e491201dd3",
    "transactionHash": "0x7ff1a69326d64507a306a836128aa67503972cb38e22fa6db217ec553c560d76",
    "transactionIndex": 0
    """
    transaction_hash = serializers.RegexField(HASH_REGEX.regex, source='eth_action_id', max_length=66)

    class Meta:
        model = TransactionReceipt
        exclude = ('eth_action',)


class EventSerializer(serializers.ModelSerializer):
    """
      {
        "address": "0x25Ff5dc79A7c4e34254ff0f4a19d69E491201DD3",
        "blockNumber": 3,
        "transactionHash": "0xc18a24a35052a5a3375ee6c2c5ddd6b0587cfa950b59468b67f63f284e2cc382",
        "transactionIndex": 0,
        "blockHash": "0x62469a8d113b27180c139d88a25f0348bb4939600011d33382b98e10842c85d9",
        "logIndex": 0,
        "removed": false,
        "id": "log_25652065",
        "returnValues": {
          "0": "0xFCaf25bF38E7C86612a25ff18CB8e09aB07c9885",
          "shipTokenContractAddress": "0xFCaf25bF38E7C86612a25ff18CB8e09aB07c9885"
        },
        "event": "SetTokenContractAddressEvent",
        "signature": "0xbbbf32f08c8c0621e580dcf0a8e0024525ec357db61bb4faa1a639d4f958a824",
        "raw": {
          "data": "0x000000000000000000000000fcaf25bf38e7c86612a25ff18cb8e09ab07c9885",
          "topics": [
            "0xbbbf32f08c8c0621e580dcf0a8e0024525ec357db61bb4faa1a639d4f958a824"
          ]
        }
      }
    """
    block_hash = serializers.CharField(source='blockHash')
    block_number = serializers.IntegerField(source='blockNumber')
    log_index = serializers.IntegerField(source='logIndex')
    event_id = serializers.CharField(source='id')
    return_values = serializers.JSONField(source='returnValues')
    event_name = serializers.CharField(source='event')
    raw = serializers.JSONField()

    transaction_hash = serializers.CharField(source='transactionHash')
    transaction_index = serializers.IntegerField(source='transactionIndex')

    class Meta:
        model = Event
        fields = ['block_hash', 'block_number', 'log_index', 'event_id', 'return_values', 'event_name',
                  'transaction_hash', 'transaction_index', 'removed', 'signature', 'raw', 'address']

    def to_internal_value(self, data):
        if 'blockHash' in data:
            data['block_hash'] = data['blockHash']
        if 'blockNumber' in data:
            data['block_number'] = data['blockNumber']
        if 'logIndex' in data:
            data['log_index'] = data['logIndex']
        if 'id' in data:
            data['event_id'] = data['id']
        if 'returnValues' in data:
            data['return_values'] = data['returnValues']
        if 'event' in data:
            data['event_name'] = data['event']
        if 'transactionHash' in data:
            data['transaction_hash'] = data['transactionHash']
        if 'transactionIndex' in data:
            data['transaction_index'] = data['transactionIndex']
        return super(EventSerializer, self).to_internal_value(data)


class EthActionSerializer(serializers.ModelSerializer):
    transaction = serializers.ResourceRelatedField(queryset=Transaction.objects.all())
    transaction_receipt = serializers.ResourceRelatedField(source='transactionreceipt',
                                                           queryset=TransactionReceipt.objects.all())

    class Meta:
        model = EthAction
        fields = '__all__'

    included_serializers = {
        'transaction': TransactionSerializer,
        'transaction_receipt': TransactionReceiptSerializer,
        'async_job': AsyncJobSerializer,
        'shipment': FKShipmentSerializer
    }

    class JSONAPIMeta:
        included_resources = ['transaction', 'transaction_receipt', 'async_job']
