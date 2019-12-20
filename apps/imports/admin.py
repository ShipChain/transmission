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

from apps.admin import pretty_json_print
from .models import ShipmentImport


class ShipmentImportsAdmin(admin.ModelAdmin):
    list_per_page = settings.ADMIN_PAGE_SIZE

    list_display = (
        'id',
        'owner_id',
        'file_type',
        'upload_status',
        'processing_status',
    )

    exclude = ('report', )

    readonly_fields = ('report_display', )

    list_filter = [
        ('created_at', DateRangeFilter),
        ('updated_at', DateRangeFilter),
        ('file_type', EnumFieldListFilter),
        ('upload_status', EnumFieldListFilter),
        ('processing_status', EnumFieldListFilter),
    ]

    search_fields = ('id', 'name', 'description', 'owner_id', 'shipment__id', 'storage_credentials_id',
                     'shipper_wallet_id', 'carrier_wallet_id', 'owner_id', 'masquerade_id', )

    def report_display(self, obj):
        return pretty_json_print(obj.report, indent=4, sort_keys=False, lineseparator=u'\n\n')

    report_display.short_description = "Report"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


admin.site.register(ShipmentImport, ShipmentImportsAdmin)
