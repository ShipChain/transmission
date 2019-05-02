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

from django.db import models

from simple_history.models import HistoricalRecords, ModelChange, ModelDelta, _model_to_dict


def get_user(request=None, **kwargs):
    if request and request.user:
        return request.user.id
    return None


class HistoricalChangesMixin:

    def diff(self, old_history):
        if self is not None and old_history is not None:
            if not isinstance(old_history, type(self)):
                raise TypeError(
                    f"unsupported type(s) for diffing: '{type(self)}' and '{type(old_history)}'")

        changes = []
        changed_fields = []
        if hasattr(self, 'instance'):
            current_values = _model_to_dict(self.instance)
        else:
            current_values = _model_to_dict(self)

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

        return ModelDelta(changes, changed_fields, old_history, self)


class TxmHistoricalRecords(HistoricalRecords):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.bases += (HistoricalChangesMixin,)
        self.manager_name = 'history'
        self.user_id_field = True
        self.get_user = get_user

    def _get_history_user_fields(self):
        if self.user_id_field:
            # We simply track the updated_by field
            history_user_fields = {
                "history_user": models.CharField(null=True, blank=True, max_length=36),
            }
        else:
            history_user_fields = {}

        return history_user_fields
