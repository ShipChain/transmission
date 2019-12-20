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

from apps.admin import shipment_admin_link
from .models import Document


class ShipmentDocumentAdmin(admin.ModelAdmin):
    list_per_page = settings.ADMIN_PAGE_SIZE

    list_display = (
        'id',
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

    def shipment_display(self, obj):
        return shipment_admin_link(obj.shipment)

    shipment_display.short_description = "Shipment"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


admin.site.register(Document, ShipmentDocumentAdmin)
