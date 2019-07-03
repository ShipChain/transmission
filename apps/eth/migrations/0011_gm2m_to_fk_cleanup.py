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

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('eth', '0010_gm2m_to_fk_data'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='ethlistener',
            name='eth_action',
        ),
        migrations.RemoveField(
            model_name='ethlistener',
            name='listener_type',
        ),
        migrations.RemoveField(
            model_name='ethaction',
            name='listeners',
        ),
        migrations.AlterField(
            model_name='ethaction',
            name='shipment',
            field=models.ForeignKey(null=False, on_delete=django.db.models.deletion.CASCADE, to='shipments.Shipment'),
            preserve_default=False,
        ),
        migrations.DeleteModel(
            name='EthListener',
        ),
    ]
