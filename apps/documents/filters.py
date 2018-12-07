from django_filters import rest_framework as filters

from .models import Document


class DocumentFilterSet(filters.FilterSet):

    class Meta:
        model = Document
        fields = ('file_type', 'document_type', 'upload_status',)
