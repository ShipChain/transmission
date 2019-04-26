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

import json

from django.core.serializers import serialize
from django.db import models

from simple_history.models import HistoricalRecords, ModelChange, ModelDelta


RELATED_TO_LOCATION = ('shipment_to', 'shipment_from', 'shipment_dest', 'shipment_bill', )


def get_user(request=None, instance=None):

    if request:
        return request.user.id

    if instance:
        if hasattr(instance, 'updated_by'):
            return instance.updated_by
        for related in RELATED_TO_LOCATION:
            if hasattr(instance, related):
                return getattr(instance, related).updated_by

    return None


def _model_to_dict(model):
    return json.loads(serialize("json", [model]))[0]["fields"]


class TxmHistoricalRecords(HistoricalRecords):

    def _get_history_user_fields(self):
        if self.user_id_field:
            # We simply track the updated_by field
            history_user_fields = {
                "history_user": models.CharField(null=True, blank=True, max_length=36),
            }
        else:
            history_user_fields = {}

        return history_user_fields


class TxmHistoricalChanges:
    def __init__(self, new_obj):
        self.obj = new_obj

    def diff_against(self, old_history):
        if self.obj is not None and old_history is not None:
            if not isinstance(old_history, type(self.obj)):
                raise TypeError(
                    f"unsupported type(s) for diffing: '{type(self.obj)}' and '{type(old_history)}'")

        changes = []
        changed_fields = []
        if hasattr(self.obj, 'instance'):
            current_values = _model_to_dict(self.obj.instance)
        else:
            current_values = _model_to_dict(self.obj)

        if not old_history:
            old_values = {f: None for f in current_values.keys()}
        else:
            old_values = _model_to_dict(old_history.instance)

        for field, new_value in current_values.items():
            if field in old_values:
                old_value = old_values[field]
                if old_value != new_value:
                    change = ModelChange(field, old_value, new_value)
                    changes.append(change)
                    changed_fields.append(field)

        return ModelDelta(changes, changed_fields, old_history, self.obj)
