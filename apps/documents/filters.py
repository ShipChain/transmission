from functools import partial

from django_filters import CharFilter
from django_filters import rest_framework as filters

from .models import Document
from apps.utils import generic_filter_enum


filter_enum = partial(generic_filter_enum, module_ref='apps.documents.models')


class DocumentFilterSet(filters.FilterSet):
    file_type = CharFilter(method=filter_enum)
    document_type = CharFilter(method=filter_enum)
    upload_status = CharFilter(method=filter_enum)

    class Meta:
        model = Document
        fields = ('document_type', 'upload_status', 'file_type',)
