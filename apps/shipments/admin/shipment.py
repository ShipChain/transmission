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
from django.utils.html import format_html
from rangefilter.filter import DateRangeFilter

from apps.shipments.models import Shipment, Location, TransitState
from apps.jobs.models import AsyncJob
from apps.admin import object_detail_admin_link

from .filter import StateFilter
from .historical import BaseModelHistory


class AsyncJobInlineTab(admin.TabularInline):
    model = AsyncJob
    fields = (
        'job_id',
        'state',
        'method',
        'created_at',
        'last_try',
    )
    readonly_fields = (
        'job_id',
        'state',
        'method',
        'created_at',
        'last_try',
    )

    def method(self, obj):
        try:
            params = obj.parameters
            return params['rpc_method']
        except KeyError:
            pass
        return "??"

    def job_id(self, obj):
        return object_detail_admin_link(obj)

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


NON_SCHEMA_FIELDS = [
    'asyncjob',
    'ethaction',
    'permissionlink',
    'loadshipment',
    'trackingdata',
    'document',
    'id',
    'owner_id',
    'storage_credentials_id',
    'vault_id',
    'vault_uri',
    'device',
    'shipper_wallet_id',
    'carrier_wallet_id',
    'moderator_wallet_id',
    'updated_at',
    'created_at',
    'contract_version',
    'updated_by',
    'state',
    'delayed',
    'expected_delay_hours',
    'exception'
]


class ShipmentAdmin(admin.ModelAdmin):
    list_per_page = settings.ADMIN_PAGE_SIZE

    # Read Only admin page until this feature is worked
    list_display = ('id', 'owner_id', 'shippers_reference', 'created_at', 'updated_at', 'shipment_state', )
    fieldsets = (
        (None, {
            'classes': ('extrapretty', ),
            'fields': (
                'id',
                ('updated_at', 'created_at',),
                ('owner_id', 'updated_by',),
                ('shipper_wallet_id', 'carrier_wallet_id', 'moderator_wallet_id',),
                ('storage_credentials_id', 'vault_id',),
                'state',
                'vault_uri',
                'device',
                'contract_version',
            )
        }),
        ('Shipment Schema Fields', {
            'classes': ('collapse',),
            'description': f'Fields in the {format_html("<a href={}>Schema</a>", "http://schema.shipchain.io")}',
            'fields': [field.name for field in Shipment._meta.get_fields() if field.name not in NON_SCHEMA_FIELDS]
        })
    )

    inlines = [
        AsyncJobInlineTab,
    ]

    search_fields = ('id', 'shipper_wallet_id', 'carrier_wallet_id', 'moderator_wallet_id', 'state', 'owner_id',
                     'ship_from_location__name', 'ship_to_location__name', 'final_destination_location__name',
                     'bill_to_location__name', )

    list_filter = [
        ('created_at', DateRangeFilter),
        ('updated_at', DateRangeFilter),
        ('delayed', admin.BooleanFieldListFilter),
        ('state', StateFilter),
    ]

    def shipment_state(self, obj):
        return TransitState(obj.state).label.upper()

    shipment_state.short_description = 'state'

    def has_delete_permission(self, request, obj=None):
        return False

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


class HistoricalShipmentAdmin(BaseModelHistory, ShipmentAdmin):
    readonly_fields = [field.name for field in Shipment._meta.get_fields()]


class LocationAdmin(BaseModelHistory):
    list_per_page = settings.ADMIN_PAGE_SIZE

    fieldsets = [(None, {'fields': [field.name for field in Location._meta.local_fields]})]

    readonly_fields = [field.name for field in Location._meta.get_fields()]

    search_fields = ('id', 'name__contains', )
