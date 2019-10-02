from django.conf import settings
from django.db import models
from django_extensions.db.fields.json import JSONField
from rest_framework.reverse import reverse

from apps.jobs.models import AsyncJob
from apps.shipments.models import Shipment
from apps.utils import random_id
from .fields import AddressField, HashField


class EthAction(models.Model):
    transaction_hash = HashField(primary_key=True)

    async_job = models.ForeignKey(AsyncJob, on_delete=models.CASCADE)

    updated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    shipment = models.ForeignKey(Shipment, on_delete=models.CASCADE)


class Transaction(models.Model):
    """
    "hash": "0x9fc76417374aa880d4449a1f7f31ec597f00b1f6f3dd2d66f4c9c6c445836d8b",
    "nonce": 2,
    "chainId": 1337,
    "to": "0x6295ee1b4f6dd65047762f924ecd367c17eabf8f",
    "value": '123450000000000000',
    "gas": 314159,
    "gasPrice": '2000000000000',
    "data": "0x57cb2fc4"
    """
    eth_action = models.OneToOneField(EthAction, db_column="hash", primary_key=True, on_delete=models.CASCADE)

    nonce = models.CharField(max_length=32)
    chain_id = models.BigIntegerField()
    to_address = AddressField()
    value = models.CharField(max_length=32)
    gas_limit = models.CharField(max_length=32)
    gas_price = models.CharField(max_length=32)
    data = models.TextField()

    @staticmethod
    def from_unsigned_tx(camel_tx):
        return Transaction(
            nonce=camel_tx['nonce'],
            chain_id=camel_tx['chainId'],
            to_address=camel_tx['to'],
            value=camel_tx['value'],
            gas_limit=camel_tx['gasLimit'] if 'gasLimit' in camel_tx else '0',
            gas_price=camel_tx['gasPrice'] if 'gasPrice' in camel_tx else '0',
            data=camel_tx['data']
        )


class TransactionReceipt(models.Model):
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

    block_hash = HashField(null=True)
    block_number = models.BigIntegerField(null=True)
    contract_address = AddressField(null=True)
    cumulative_gas_used = models.IntegerField(null=True)
    from_address = AddressField()
    gas_used = models.IntegerField(null=True)
    logs = JSONField(null=True)
    logs_bloom = models.CharField(max_length=514, null=True)
    status = models.BooleanField(null=True)
    to_address = AddressField(null=True)
    loom_tx_hash = HashField(null=True, db_index=True)
    eth_action = models.OneToOneField(EthAction, db_column="transaction_hash",
                                      primary_key=True, on_delete=models.CASCADE)
    transaction_index = models.IntegerField(null=True)

    @staticmethod
    def convert_receipt(receipt):
        if 'ethTxHash' in receipt or 'transactionHash' in receipt:
            eth_action_id = receipt['ethTxHash'] if 'ethTxHash' in receipt else receipt['transactionHash']
        else:
            eth_action_id = receipt['hash']
        return {
            'block_hash': receipt['blockHash'] if 'blockHash' in receipt else None,
            'block_number': receipt['blockNumber'] if 'blockNumber' in receipt else None,
            'contract_address': receipt['contractAddress'] if 'contractAddress' in receipt else None,
            'cumulative_gas_used': receipt['cumulativeGasUsed'] if 'cumulativeGasUsed' in receipt else None,
            'from_address': "0x0" if 'from' not in receipt else receipt['from'],
            'gas_used': receipt['gasUsed'] if 'gasUsed' in receipt else None,
            'logs': receipt['logs'] if 'logs' in receipt else None,
            'logs_bloom': receipt['logsBloom'] if 'logsBloom' in receipt else None,
            'status': receipt['status'] if 'status' in receipt else None,
            'to_address': receipt['to'] if 'to' in receipt else None,
            'loom_tx_hash': receipt['transactionHash'] if 'ethTxHash' in receipt else None,
            'eth_action_id': eth_action_id,
            'transaction_index': receipt['transactionIndex'] if 'transactionIndex' in receipt else None,
        }

    @staticmethod
    def from_eth_receipt(receipt):
        return TransactionReceipt(
            block_hash=receipt['blockHash'],
            block_number=receipt['blockNumber'],
            contract_address=receipt['contractAddress'],
            cumulative_gas_used=receipt['cumulativeGasUsed'],
            from_address="0x0" if 'from' not in receipt else receipt['from'],
            gas_used=receipt['gasUsed'],
            logs=receipt['logs'],
            logs_bloom=receipt['logsBloom'] if 'logsBloom' in receipt else None,
            status=receipt['status'],
            to_address=receipt['to'] if 'to' in receipt else None,
            loom_tx_hash=receipt['transactionHash'] if 'ethTxHash' in receipt else None,
            eth_action_id=receipt['transactionHash'] if 'ethTxHash' not in receipt else receipt['ethTxHash'],
            transaction_index=receipt['transactionIndex'],
        )


class Event(models.Model):
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

    id = models.CharField(primary_key=True, default=random_id, max_length=36)
    eth_action = models.ForeignKey(EthAction, on_delete=models.CASCADE, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    address = AddressField()
    block_number = models.BigIntegerField()
    transaction_hash = HashField()
    transaction_index = models.IntegerField()
    block_hash = HashField()
    log_index = models.IntegerField()
    removed = models.BooleanField()
    event_id = models.CharField(max_length=514)
    return_values = JSONField()
    event_name = models.CharField(max_length=514)
    signature = HashField()
    raw = JSONField()

    @staticmethod
    def get_event_subscription_url():
        return settings.INTERNAL_URL + reverse('event-list', kwargs={'version': 'v1'})
