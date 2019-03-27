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

from apps.jobs.models import AsyncActionType
from .models import EscrowState, ShipmentState
from .rpc import RPCClientFactory
from .serializers import ShipmentVaultSerializer

LOG = logging.getLogger('transmission')


class LoadEventHandler:
    @staticmethod
    def handle(event, shipment):
        LOG.debug(f'Handling {event.event_name} Event')
        method = underscore(event.event_name)
        getattr(LoadEventHandler, method)(event, shipment)

    @staticmethod
    def shipment_created(event, shipment):
        shipment.loadshipment.shipper = event.return_values['msgSender']
        shipment.loadshipment.shipment_state = ShipmentState.CREATED
        shipment.loadshipment.save()

        # Add vault data to new Shipment
        rpc_client = RPCClientFactory.get_client()
        signature = rpc_client.add_shipment_data(shipment.storage_credentials_id, shipment.shipper_wallet_id,
                                                 shipment.vault_id, ShipmentVaultSerializer(shipment).data)

        # Update LOAD contract with initial shipment data
        shipment.set_carrier()
        if shipment.moderator_wallet_id:
            shipment.set_moderator()
        shipment.set_vault_uri(shipment.vault_uri)
        shipment.set_vault_hash(signature['hash'], action_type=AsyncActionType.SHIPMENT, rate_limit=0)

    @staticmethod
    def shipment_carrier_set(event, shipment):
        shipment.loadshipment.carrier = event.return_values['carrier']
        shipment.loadshipment.save()

    @staticmethod
    def shipment_moderator_set(event, shipment):
        shipment.loadshipment.moderator = event.return_values['moderator']
        shipment.loadshipment.save()

    @staticmethod
    def shipment_in_progress(event, shipment):
        shipment.loadshipment.shipment_state = ShipmentState.IN_PROGRESS
        shipment.loadshipment.save()

    @staticmethod
    def shipment_complete(event, shipment):
        shipment.loadshipment.shipment_state = ShipmentState.COMPLETE
        shipment.loadshipment.save()

        shipment.device_id = None
        shipment.save()

    @staticmethod
    def shipment_canceled(event, shipment):
        shipment.loadshipment.shipment_state = ShipmentState.CANCELED
        shipment.loadshipment.save()

    @staticmethod
    def vault_uri(event, shipment):
        shipment.loadshipment.vault_uri = event.return_values['vaultUri']
        shipment.loadshipment.save()

    @staticmethod
    def vault_hash(event, shipment):
        shipment.loadshipment.vault_hash = event.return_values['vaultHash']
        shipment.loadshipment.save()

    @staticmethod
    def escrow_deposited(event, shipment):
        shipment.loadshipment.funded_amount += event.return_values['amount']
        shipment.loadshipment.save()

    @staticmethod
    def escrow_funded(event, shipment):
        shipment.loadshipment.escrow_state = EscrowState.FUNDED
        shipment.loadshipment.save()

    @staticmethod
    def escrow_released(event, shipment):
        shipment.loadshipment.escrow_state = EscrowState.RELEASED
        shipment.loadshipment.save()

    @staticmethod
    def escrow_refunded(event, shipment):
        shipment.loadshipment.escrow_state = EscrowState.REFUNDED
        shipment.loadshipment.save()

    @staticmethod
    def escrow_withdrawn(event, shipment):
        shipment.loadshipment.escrow_state = EscrowState.WITHDRAWN
        shipment.loadshipment.save()

    @staticmethod
    def escrow_created(event, shipment):
        shipment.loadshipment.funding_type = event.return_values['fundingType']
        shipment.loadshipment.contracted_amount = event.return_values['contractedAmount']
        shipment.loadshipment.created_at = event.return_values['createdAt']
        shipment.loadshipment.refund_address = event.return_values['msgSender']
        shipment.loadshipment.shipment_state = EscrowState.CREATED
        shipment.loadshipment.save()
