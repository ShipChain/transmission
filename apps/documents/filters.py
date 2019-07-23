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

from functools import partial

from django_filters import CharFilter
from django_filters import rest_framework as filters

from apps.utils import generic_filter_enum
from .models import Document


# pylint:disable=invalid-name
filter_enum = partial(generic_filter_enum, module_ref='apps.documents.models')


class DocumentFilterSet(filters.FilterSet):
    file_type = CharFilter(method=filter_enum)
    document_type = CharFilter(method=filter_enum)
    upload_status = CharFilter(method=filter_enum)

    class Meta:
        model = Document
        fields = ('document_type', 'upload_status', 'file_type',)
