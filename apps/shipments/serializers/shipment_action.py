"""
Copyright 2019 ShipChain, Inc.

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

from functools import partial

from django_fsm import can_proceed
from enumfields import Enum
from rest_framework import exceptions
from rest_framework_json_api import serializers
from shipchain_common.utils import UpperEnumField

from apps.shipments.models import Shipment, TransitState


class ActionType(Enum):
    PICK_UP = partial(Shipment.pick_up)
    ARRIVAL = partial(Shipment.arrival)
    DROP_OFF = partial(Shipment.drop_off)


class ShipmentActionRequestSerializer(serializers.Serializer):
    action_type = UpperEnumField(ActionType, lenient=True, ints_as_names=True)
    tracking_data = serializers.CharField(required=False, allow_null=True)
    document_id = serializers.CharField(required=False, allow_null=True)
    raw_asset_physical_id = serializers.CharField(required=False, allow_null=True)

    def validate_action_type(self, action_type):
        shipment = self.context['shipment']
        action_type.value.func.__self__ = shipment  # Hack for getting dynamic partial funcs to work w/ can_proceed
        if not can_proceed(action_type.value.func):
            # Bad state transition
            raise exceptions.ValidationError(f'Action {action_type.name} not available while Shipment '
                                             f'is in state {TransitState(shipment.state).name}')
        return action_type
