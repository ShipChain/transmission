from functools import partial

from django_filters import CharFilter
from django_filters import rest_framework as filters


from .models import ShipmentImport
from apps.utils import generic_filter_enum

filter_enum = partial(generic_filter_enum, module_ref='apps.imports.models')


class ShipmentImportFilterSet(filters.FilterSet):
    csv_file_type = CharFilter(method=filter_enum)
    upload_status = CharFilter(method=filter_enum)
    processing_status = CharFilter(method=filter_enum)

    class Meta:
        model = ShipmentImport
        fields = ('name', 'upload_status', 'file_type', 'processing_status', )
