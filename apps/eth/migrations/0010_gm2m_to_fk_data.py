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


def migrate_relationships(apps, schema_editor):
    EthAction = apps.get_model('eth', 'EthAction')
    for ethaction in EthAction.objects.all():
        listener = ethaction.ethlistener_set.first()
        if listener:
            ethaction.shipment_id = listener.listener_id
            ethaction.save()

    EthAction.objects.filter(shipment_id=None).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('eth', '0009_nullable_gm2m'),
    ]

    operations = [
        migrations.RunPython(code=migrate_relationships, reverse_code=migrations.RunPython.noop)
    ]
