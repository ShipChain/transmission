#  Copyright 2019 ShipChain, Inc.
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.


from django.db import migrations
from enumfields import Enum


class TransitState(Enum):
    AWAITING_PICKUP = 10
    IN_TRANSIT = 20
    AWAITING_DELIVERY = 30
    DELIVERED = 40

    @classmethod
    def choices(cls):
        return tuple((m.value, m.name) for m in cls)


def set_initial_states(apps, schema_editor):
    """
    Backpopulate correct state based on pickup_act and delivery_act
    """
    Shipment = apps.get_model('shipments', 'Shipment')

    for shipment in Shipment.objects.all():
        if shipment.pickup_act:
            if shipment.delivery_act:
                state = TransitState.DELIVERED
            else:
                state = TransitState.IN_TRANSIT

            Shipment.objects.filter(id=shipment.id).update(state=state.value)


class Migration(migrations.Migration):

    dependencies = [
        ('shipments', '0038_shipment_states'),
    ]

    operations = [
        migrations.RunPython(
            code=set_initial_states, reverse_code=migrations.RunPython.noop
        ),
    ]
