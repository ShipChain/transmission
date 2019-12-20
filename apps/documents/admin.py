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

from django.conf import settings
from django.contrib import admin
from enumfields.admin import EnumFieldListFilter
from rangefilter.filter import DateRangeFilter

from apps.admin import ShipmentAdminDisplayMixin, NoAddUpdateDeletePermissionMixin
from .models import Document


class ShipmentDocumentAdmin(NoAddUpdateDeletePermissionMixin,
                            ShipmentAdminDisplayMixin,
                            admin.ModelAdmin):
    list_per_page = settings.ADMIN_PAGE_SIZE

    list_display = (
        'id',
        'shipment_display',
        'owner_id',
        'document_type',
        'file_type',
        'upload_status',
    )

    list_filter = [
        ('created_at', DateRangeFilter),
        ('updated_at', DateRangeFilter),
        ('upload_status', EnumFieldListFilter),
        ('file_type', EnumFieldListFilter),
        ('document_type', EnumFieldListFilter),
    ]

    exclude = ('shipment', )

    readonly_fields = (
        'shipment_display',
    )

    search_fields = (
        'id',
        'name',
        'description',
        'owner_id',
        'shipment__id',
    )


admin.site.register(Document, ShipmentDocumentAdmin)
