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

import importlib

from django_filters import CharFilter
from django_filters import rest_framework as filters
from enumfields.drf import EnumField
from inflection import camelize

from .models import ShipmentImport


def filter_enum(queryset, name, value):
    enum_name = camelize(name)
    enum_class = getattr(importlib.import_module('.models', __package__), enum_name)

    # Use case insensitive search (lenient=True, to_internal_value) to convert input string to enum value
    file_type_field = EnumField(enum_class, lenient=True, read_only=True, ints_as_names=True)
    enum_value = file_type_field.to_internal_value(value)
    queryset = queryset.filter(**{name: enum_value})
    return queryset


class ShipmentImportFilterSet(filters.FilterSet):
    file_type = CharFilter(method=filter_enum)
    upload_status = CharFilter(method=filter_enum)
    processing_status = CharFilter(method=filter_enum)
    name__contains = CharFilter(field_name='name', lookup_expr='icontains')

    class Meta:
        model = ShipmentImport
        fields = ('upload_status', 'file_type', 'processing_status', )
