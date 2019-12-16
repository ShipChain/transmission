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

import pytz
from dateutil.parser import parse
from django.conf import settings
from shipchain_common.utils import UpperEnumField

from apps.shipments.models import Location, ExceptionType, TransitState
from apps.documents.models import DocumentType, FileType
from apps.utils import UploadStatus


class ChangesDiffSerializer:
    relation_fields = settings.RELATED_FIELDS_WITH_HISTORY_MAP.keys()
    excluded_fields = ('history_user', 'version', 'customer_fields', 'geometry',
                       'background_data_hash_interval', 'manual_update_hash_interval', 'shipment', )

    # Enum field serializers
    state_enum_serializer = UpperEnumField(TransitState, lenient=True, ints_as_names=True, read_only=True)
    exception_enum_serializer = UpperEnumField(ExceptionType, lenient=True, ints_as_names=True, read_only=True)
    file_type_enum_serializer = UpperEnumField(FileType, lenient=True, ints_as_names=True, read_only=True)
    upload_status_enum_serializer = UpperEnumField(UploadStatus, lenient=True, ints_as_names=True, read_only=True)
    document_type_enum_serializer = UpperEnumField(DocumentType, lenient=True, ints_as_names=True, read_only=True)

    def __init__(self, queryset, request):
        self.queryset = queryset
        self.request = request

    def diff_object_fields(self, old, new):
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
                    # The relationship field is created
                    field['new'] = Location.history.filter(pk=change.new).first().instance.id
                if change.old and change.new:
                    # The relationship field has been modified no need to include it in flat changes
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
                related_changes = self.build_list_changes(changes, json_field=True, base_field=field_name)
                if related_changes:
                    changes_list.extend(related_changes)
        return changes_list

    def document_actions(self, new_obj):
        document_queryset = new_obj.historicaldocument_set.all().filter(upload_status=UploadStatus.COMPLETE)
        if document_queryset.count() > 0:
            for hist_doc in document_queryset:
                yield {
                    'history_date': hist_doc.history_date,
                    'fields': None,
                    'relationships': {
                        'documents': {
                            'id': hist_doc.id,
                            'fields': self.build_list_changes(hist_doc.diff(hist_doc.prev_record))
                        }
                    },
                    'author': hist_doc.history_user
                }

    def datetime_filters(self, changes_diff):
        gte_datetime = self.request.query_params.get('history_date__gte')
        lte_datetime = self.request.query_params.get('history_date__lte')

        if lte_datetime:
            lte_datetime = parse(lte_datetime).astimezone(pytz.utc)
            changes_diff = list(filter(lambda change: change['history_date'] <= lte_datetime, changes_diff))

        if gte_datetime:
            gte_datetime = parse(gte_datetime).astimezone(pytz.utc)
            changes_diff = list(filter(lambda change: change['history_date'] >= gte_datetime, changes_diff))

        return changes_diff

    @property
    def data(self):
        queryset = self.queryset
        count = queryset.count()

        queryset_diff = []
        if count == 0:
            return queryset_diff
        index = 0
        if count > 1:
            while index + 1 < count:
                new = queryset[index]
                old = queryset[index + 1]
                index += 1
                queryset_diff.extend(list(self.document_actions(new)))
                queryset_diff.append(self.diff_object_fields(old, new))

            # The diff change for the shipment creation object is computed against a None object
            queryset_diff.append(self.diff_object_fields(None, queryset[index]))

        return self.datetime_filters(queryset_diff)
