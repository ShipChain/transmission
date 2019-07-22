import importlib
from functools import partial

from django_filters import CharFilter
from django_filters import rest_framework as filters
from enumfields.drf import EnumField
from inflection import camelize

from .models import Document
from apps.utils import generic_filter_enum


# def filter_enum(queryset, name, value):
#     enum_name = camelize(name)
#     enum_class = getattr(importlib.import_module('.models', __package__), enum_name)
#
#     # Use case insensitive search (lenient=True, to_internal_value) to convert input string to enum value
#     file_type_field = EnumField(enum_class, lenient=True, read_only=True, ints_as_names=True)
#     enum_value = file_type_field.to_internal_value(value)
#     queryset = queryset.filter(**{name: enum_value})
#     return queryset

filter_enum = partial(generic_filter_enum, module_ref='apps.documents.models')


class DocumentFilterSet(filters.FilterSet):
    file_type = CharFilter(method=filter_enum)
    document_type = CharFilter(method=filter_enum)
    upload_status = CharFilter(method=filter_enum)

    class Meta:
        model = Document
        fields = ('document_type', 'upload_status', 'file_type',)
