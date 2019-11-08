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
import copy
import logging
from functools import lru_cache

from django.conf import settings
from django.db import models
from django.utils.timezone import now
from django.db.models.fields.proxy import OrderWrt

from simple_history.signals import post_create_historical_record, pre_create_historical_record
from simple_history.models import HistoricalRecords, ModelChange, ModelDelta, transform_field, _model_to_dict


LOG = logging.getLogger('transmission')


def get_user(request=None, **kwargs):
    if request and request.user:
        return request.user.id
    return None


class HistoricalChangesMixin:

    def diff(self, old_history, json_fields_only=False):
        changes_map = {}
        current_values = None
        if json_fields_only and hasattr(self, 'instance'):
            for field_name in self.json_fields:
                current_values = getattr(self, field_name, None)
                old_values = getattr(old_history, field_name, None)
                if not old_values and isinstance(current_values, dict):
                    old_values = {f: None for f in current_values.keys()}
                elif not current_values and isinstance(old_values, dict):
                    current_values = {f: None for f in old_values.keys()}
                elif not old_values and not current_values:
                    continue
                changes_map[field_name] = self.build_changes(current_values, old_values, old_history,
                                                             from_json_field=True)
        elif hasattr(self, 'instance'):
            current_values = _model_to_dict(self.instance)
        else:
            current_values = _model_to_dict(self)

        if not old_history and not json_fields_only:
            old_values = {f: None for f in current_values.keys()}
        elif old_history:
            old_values = _model_to_dict(old_history.instance)

        to_return = changes_map if json_fields_only else self.build_changes(current_values, old_values, old_history)
        return to_return

    def build_changes(self, new_obj_dict, old_obj_dict, old_historical_obj, from_json_field=False):
        changes = []
        changed_fields = []
        for field, new_value in new_obj_dict.items():
            if field in old_obj_dict:
                old_value = old_obj_dict[field]
                if old_value != new_value:
                    change = ModelChange(field, old_value, new_value)
                    changes.append(change)
                    changed_fields.append(field)
            elif from_json_field:
                change = ModelChange(field, None, new_value)
                changes.append(change)
                changed_fields.append(field)

        return ModelDelta(changes, changed_fields, old_historical_obj, self)

    @property
    @lru_cache()
    def json_fields(self):
        list_json_fields = []
        for field in self.instance._meta.get_fields():
            if field.__class__.__name__.lower() == 'jsonfield':
                list_json_fields.append(field.name)
        return list_json_fields


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

    def copy_fields(self, model):
        fields = {}
        for field in self.fields_included(model):
            field = copy.copy(field)
            field.remote_field = copy.copy(field.remote_field)
            if isinstance(field, OrderWrt):
                field.__class__ = models.IntegerField
            if isinstance(field, models.ForeignKey):
                old_field = field
                old_swappable = old_field.swappable
                old_field.swappable = False
                try:
                    _name, _path, args, field_args = old_field.deconstruct()
                finally:
                    old_field.swappable = old_swappable

                if getattr(old_field, "one_to_one", False) or \
                        isinstance(old_field, (models.OneToOneField, models.ForeignKey)):
                    field_type = models.ForeignKey

                    if old_field.name in settings.RELATED_FIELDS_WITH_HISTORY_MAP.keys():
                        field_args["to"] = f'shipments.Historical' \
                                           f'{settings.RELATED_FIELDS_WITH_HISTORY_MAP[old_field.name]}'
                else:
                    field_type = type(old_field)

                if field_args.get("to", None) == "self":
                    field_args["to"] = old_field.model

                # Override certain arguments passed when creating the field
                # so that they work for the historical field.
                field_args.update(
                    db_constraint=False,
                    null=True,
                    blank=True,
                    primary_key=False,
                    db_index=True,
                    serialize=True,
                    unique=False,
                    on_delete=models.DO_NOTHING,
                )
                field = field_type(*args, **field_args)
                field.name = old_field.name
            else:
                transform_field(field)
            fields[field.name] = field
        return fields

    def create_historical_record(self, instance, history_type, using=None):
        history_date = getattr(instance, "_history_date", now())
        history_user = self.get_history_user(instance)
        history_change_reason = getattr(instance, "changeReason", None)
        manager = getattr(instance, self.manager_name)

        attrs = {}
        for field in self.fields_included(instance):
            related_instance = getattr(instance, field.name, None)
            if related_instance and hasattr(related_instance, 'history'):
                attrs[field.name] = related_instance.history.first()
            else:
                attrs[field.name] = getattr(instance, field.name)

        history_instance = manager.model(
            history_date=history_date,
            history_type=history_type,
            history_user=history_user,
            history_change_reason=history_change_reason,
            **attrs
        )

        pre_create_historical_record.send(
            sender=manager.model,
            instance=instance,
            history_date=history_date,
            history_user=history_user,
            history_change_reason=history_change_reason,
            history_instance=history_instance,
            using=using,
        )

        history_instance.save(using=using)

        post_create_historical_record.send(
            sender=manager.model,
            instance=instance,
            history_instance=history_instance,
            history_date=history_date,
            history_user=history_user,
            history_change_reason=history_change_reason,
            using=using,
        )


class AnonymousHistoricalMixin:
    @classmethod
    def get_class_instance(cls):
        return cls

    def anonymous_historical_change(self, only_history=False, history_type='~', user=None, **kwargs):
        """
        Update a shipment and / or create a related anonymous historical record.

        :param kwargs: key value fields to update.
        :param only_history: Boolean for creating a historical record without changes to the object instance
        :param history_type: Type for the historical object in creation, '+' or '~' respectively for
        created and changed
        :param user: Authoring of the historical record
        """

        def create_historical_instance(obj, h_type):
            # Manual creation of a historical object
            TxmHistoricalRecords().create_historical_record(obj, h_type)
            h_instance = obj.history.first()
            h_instance.history_user = user
            h_instance.updated_by = user
            h_instance.save()
            return h_instance

        if only_history:
            historical_object = create_historical_instance(self, history_type)
            LOG.debug(f'Created anonymous historical record: {historical_object.id}')
            return historical_object

        instance = self.get_class_instance().objects.filter(id=self.id)
        instance.update(**kwargs)
        instance = instance.first()
        historical_instance = create_historical_instance(instance, history_type)

        LOG.debug(f'Updated shipment: {instance.id}, with: {kwargs} and created related anonymous historical record: '
                  f'{historical_instance.id}')
