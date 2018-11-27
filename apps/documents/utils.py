
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from django_filters import rest_framework as filters

from .models import Document


class DocumentsPagination(PageNumberPagination):

    def get_paginated_response(self, data):
        return Response({
            'links': {
                'next': self.get_next_link(),
                'previous': self.get_previous_link()
            },
            'count': len(data),
            'documents': data
        })


class DocumentFilterSet(filters.FilterSet):

    class Meta:
        model = Document
        fields = ('file_type', 'document_type', 'upload_status',)
