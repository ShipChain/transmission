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

from django.contrib import admin
from django.utils.html import format_html
from rangefilter.filter import DateRangeFilter

from apps.shipments.models import Shipment, Location, TransitState
from apps.jobs.models import AsyncJob
from apps.admin import object_detail_admin_link, AdminPageSizeMixin, ReadOnlyPermissionMixin

from .filter import StateFilter
from .historical import BaseModelHistory


class AsyncJobInlineTab(ReadOnlyPermissionMixin, admin.TabularInline):
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


NON_SCHEMA_FIELDS = [
    'asyncjob',
    'ethaction',
    'permissionlink',
    'loadshipment',
    'trackingdata',
    'telemetrydata',
    'document',
    'shipmentnote',
    'shipment_tags',
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
    'exception',
    'delayed',
    'expected_delay_hours',
    'geofences',
    'assignee_id',
    'gtx_required',
    'gtx_validation',
    'gtx_validation_timestamp',
    'aftership_tracking',
    'arrival_est',
    'routeleg',
]


class ShipmentAdmin(AdminPageSizeMixin,
                    ReadOnlyPermissionMixin,
                    admin.ModelAdmin):

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

    def get_fieldsets(self, request, obj=None):
        if 'history' not in request.scope['path']:
            if 'route_link' not in self.fieldsets[0][1]['fields']:
                self.fieldsets[0][1]['fields'] = self.fieldsets[0][1]['fields'] + ('route_link',)
        elif 'route_link' in self.fieldsets[0][1]['fields']:
            self.fieldsets[0][1]['fields'] = tuple(
                [field for field in self.fieldsets[0][1]['fields'] if field != 'route_link']
            )
        return self.fieldsets

    search_fields = ('id', 'shipper_wallet_id', 'carrier_wallet_id', 'moderator_wallet_id', 'state', 'owner_id',
                     'ship_from_location__name__icontains', 'ship_to_location__name__icontains',
                     'final_destination_location__name__icontains', 'bill_to_location__name__icontains', )

    list_filter = [
        ('created_at', DateRangeFilter),
        ('updated_at', DateRangeFilter),
        ('delayed', admin.BooleanFieldListFilter),
        ('state', StateFilter),
    ]

    def shipment_state(self, obj):
        return TransitState(obj.state).label.upper()

    def route_link(self, obj):
        return object_detail_admin_link(obj.routeleg.route)
    route_link.short_description = 'Route'

    shipment_state.short_description = 'state'


class HistoricalShipmentAdmin(BaseModelHistory, ShipmentAdmin):
    readonly_fields = [field.name for field in Shipment._meta.get_fields()]


class LocationAdmin(AdminPageSizeMixin, BaseModelHistory):

    fieldsets = [(None, {'fields': [field.name for field in Location._meta.local_fields] + ['shipment_display']})]

    readonly_fields = [field.name for field in Location._meta.get_fields()] + ['shipment_display']

    search_fields = (
        'id',
        'name__icontains',
        'address_1__icontains',
        'address_2__icontains',
        'city__icontains',
        'state__icontains',
    )

    list_filter = [
        ('created_at', DateRangeFilter),
        ('updated_at', DateRangeFilter),
    ]

    list_display = (
        'id',
        'shipment_display',
        'name',
        'created_at',
        'updated_at',
    )

    def shipment_display(self, obj):
        for related_name in ('shipment_from', 'shipment_to', 'shipment_dest', 'shipment_bill', ):
            try:
                shipment = getattr(obj, related_name)
                return object_detail_admin_link(shipment)
            except AttributeError:
                continue
        return None

    shipment_display.short_description = "Shipment"
