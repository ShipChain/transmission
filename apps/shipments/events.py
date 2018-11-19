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
from inflection import underscore
from .models import EscrowState, ShipmentState
from .rpc import RPCClientFactory
from .serializers import ShipmentVaultSerializer

LOG = logging.getLogger('transmission')


class LoadEventHandler:
    @staticmethod
    def handle(event, shipment):
        method = underscore(event.event_name)
        getattr(LoadEventHandler, method)(event, shipment)

    @staticmethod
    def shipment_created(event, shipment):
        LOG.debug(f'Handling ShipmentCreated Event.')
        shipment.loadshipmenteth.shipper = event.return_values['msgSender']
        shipment.loadshipmenteth.shipment_state = ShipmentState.CREATED
        shipment.loadshipmenteth.save()

        # Add vault data to new Shipment
        rpc_client = RPCClientFactory.get_client()
        signature = rpc_client.add_shipment_data(shipment.storage_credentials_id, shipment.shipper_wallet_id,
                                                 shipment.vault_id, ShipmentVaultSerializer(shipment).data)

        # Update LOAD contract with vault uri/hash
        LOG.debug(f'Updating load contract with hash {signature["hash"]}.')
        shipment.update_vault_hash(signature['hash'])

    @staticmethod
    def escrow_created(event, shipment):
        LOG.debug(f'Handling EscrowCreated Event.')
        shipment.loadshipmenteth.funding_type = event.return_values['fundingType']
        shipment.loadshipmenteth.contracted_amount = event.return_values['contractedAmount']
        shipment.loadshipmenteth.created_at = event.return_values['createdAt']
        shipment.loadshipmenteth.refund_address = event.return_values['msgSender']
        shipment.loadshipmenteth.shipment_state = EscrowState.CREATED
        shipment.loadshipmenteth.save()

    @staticmethod
    def vault_hash(event, shipment):
        LOG.debug(f'Handling VaultHash Event.')
        shipment.loadshipmenteth.vault_hash = event.return_values['vaultHash']
        shipment.loadshipmenteth.save()
