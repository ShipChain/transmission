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


def deduplicate_events(apps, schema_editor):
    Event = apps.get_model('eth', 'Event')

    duplicate_events = Event.objects.values('transaction_hash', 'log_index').annotate(
        duplicates=models.Count('transaction_hash')).filter(duplicates__gt=1)

    for dup_event in duplicate_events:
        events = Event.objects.filter(eth_action=dup_event['transaction_hash'], log_index=dup_event['log_index']).order_by('-created_at')

        print(f'Found {events.count()} events for {dup_event["transaction_hash"]} {dup_event["log_index"]}')
        first = True
        for event in events:
            if not first:
                event.delete()
            first = False


class Migration(migrations.Migration):

    dependencies = [
        ('eth', '0002_nullable_fields'),
    ]

    operations = [
        migrations.RunPython(code=deduplicate_events, reverse_code=migrations.RunPython.noop)
    ]
