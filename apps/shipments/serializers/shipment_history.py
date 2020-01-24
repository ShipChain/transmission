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

from datetime import timedelta
from functools import lru_cache
from itertools import chain

import pytz
from dateutil.parser import parse
from django.conf import settings
from shipchain_common.utils import UpperEnumField

from apps.shipments.models import Location, Shipment, ExceptionType, TransitState
from apps.documents.models import Document, DocumentType, FileType
from apps.utils import UploadStatus


class ChangesDiffSerializer:
    _allowed_historical_classes = (Shipment, Document, )
    _many_to_one_historical_models = (Document.history.model, )

    relation_fields = settings.RELATED_FIELDS_WITH_HISTORY_MAP.keys()
    excluded_fields = ('history_user', 'version', 'customer_fields', 'geometry',
                       'background_data_hash_interval', 'manual_update_hash_interval', 'shipment', )

    # Enum field serializers
    state_enum_serializer = UpperEnumField(TransitState, lenient=True, ints_as_names=True, read_only=True)
    exception_enum_serializer = UpperEnumField(ExceptionType, lenient=True, ints_as_names=True, read_only=True)
    file_type_enum_serializer = UpperEnumField(FileType, lenient=True, ints_as_names=True, read_only=True)
    upload_status_enum_serializer = UpperEnumField(UploadStatus, lenient=True, ints_as_names=True, read_only=True)
    document_type_enum_serializer = UpperEnumField(DocumentType, lenient=True, ints_as_names=True, read_only=True)

    def __init__(self, queryset, request, shipment_id):
        self.queryset = queryset
        self.request = request
        self.shipment_id = shipment_id

    def diff_object_fields(self, old, new):

        if isinstance(new, self._many_to_one_historical_models):
            return self.build_many_to_one_changes(new, new.instance._meta.model_name + 's')

        changes = new.diff(old)

        flat_changes = self.build_list_changes(changes)
        relation_changes = self.relation_changes(new)
        flat_changes.extend(self.json_field_changes(new, old))

        return {
            'history_date': new.history_date,
            'fields': flat_changes,
            'relationships': relation_changes if relation_changes else None,
            'author': new.history_user,
        }

    def get_enum_representation(self, field_name, field_value):
        representation = field_value
        # The initial enum values are None
        if field_value is not None:
            # We wrap this in a try:except to avoid fields like Location.state
            try:
                representation = getattr(self, f'{field_name}_enum_serializer').to_representation(field_value)
            except (AttributeError, ValueError):
                pass
        return representation

    def build_list_changes(self, changes, json_field=False, base_field=None):
        field_list = []
        if changes is None:
            return field_list

        changes_list = [change for change in changes.changes if change.field not in self.excluded_fields]
        for change in changes_list:
            field = {
                'field': change.field if not json_field else f'{base_field}.{change.field}',
                'old': self.get_enum_representation(change.field, change.old),
                'new': self.get_enum_representation(change.field, change.new)
            }

            if change.field in self.relation_fields:
                if change.old is None:
                    # The relationship object is created
                    field['new'] = Location.history.filter(pk=change.new).first().instance.id
                elif change.old and change.new:
                    # The relationship object has been modified no need to include it in flat changes
                    continue

            field_list.append(field)
        return field_list

    def relation_changes(self, new_historical):
        relations_map = {}
        for relation in self.relation_fields:
            historical_relation = getattr(new_historical, relation, None)
            changes = None
            if historical_relation:
                date_max = new_historical.history_date
                date_min = date_max - timedelta(milliseconds=settings.SIMPLE_HISTORY_RELATED_WINDOW_MS)
                if new_historical.history_user == historical_relation.history_user and \
                        date_min <= historical_relation.history_date <= date_max:
                    # The relationship field has changed
                    changes = historical_relation.diff(historical_relation.prev_record)
            if changes:
                relations_map[relation] = self.build_list_changes(changes)

        return relations_map

    def json_field_changes(self, new_obj, old_obj):
        changes_list = []
        # JsonFields changes between the two historical objects
        json_fields_changes = new_obj.diff(old_obj, json_fields_only=True)
        if json_fields_changes:
            for field_name, changes in json_fields_changes.items():
                changes_list.extend(self.build_list_changes(changes, json_field=True, base_field=field_name))
        return changes_list

    def build_many_to_one_changes(self, historical_document, relation_object_name):
        return {
            'history_date': historical_document.history_date,
            'fields': None,
            'relationships': {
                relation_object_name: {
                    'id': historical_document.id,
                    'fields': self.build_list_changes(historical_document.diff(historical_document.prev_record))
                }
            },
            'author': historical_document.history_user
        }

    @property
    @lru_cache()
    def historical_queryset(self):
        historical_document_queryset = Document.history.filter(shipment__id=self.shipment_id,
                                                               upload_status=UploadStatus.COMPLETE)

        historical_queryset = list(chain(historical_document_queryset, self.queryset))

        historical_queryset.sort(key=lambda historical_object: historical_object.history_date, reverse=True)

        return historical_queryset

    def filter_queryset(self, historical_queryset):
        gte_datetime = self.request.query_params.get('history_date__gte')
        lte_datetime = self.request.query_params.get('history_date__lte')

        if lte_datetime:
            lte_datetime = parse(lte_datetime).astimezone(pytz.utc)
            historical_queryset = list(filter(lambda h_obj: h_obj.history_date <= lte_datetime, historical_queryset))

        if gte_datetime:
            gte_datetime = parse(gte_datetime).astimezone(pytz.utc)
            historical_queryset = list(filter(lambda h_obj: h_obj.history_date >= gte_datetime, historical_queryset))

        return historical_queryset

    def get_data(self, page):
        diff_changes = []

        for historical_obj in page:
            diff_changes.append(self.diff_object_fields(historical_obj.prev_record, historical_obj))

        return diff_changes
