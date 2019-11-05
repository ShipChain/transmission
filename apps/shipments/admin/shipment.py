from django.contrib import admin
from django.utils.html import format_html

from apps.shipments.models import Shipment, Location, TransitState
from apps.jobs.models import AsyncJob

from .filter import StateFilter
from .historical import BaseModelHistory


class AsyncJobInlineTab(admin.TabularInline):
    model = AsyncJob
    fields = (
        'id',
        'state',
        'method',
        'created_at',
        'last_try',
    )
    readonly_fields = (
        'id',
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
    # Read Only admin page until this feature is worked
    list_display = ('id', 'shippers_reference', 'shipment_state', )
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

    search_fields = ('id', 'shipper_wallet_id', 'carrier_wallet_id', 'moderator_wallet_id', 'state',
                     'ship_from_location__name', 'ship_to_location__name', 'final_destination_location__name',
                     'bill_to_location__name', )

    list_filter = [
        ('created_at', admin.DateFieldListFilter),
        ('delayed', admin.BooleanFieldListFilter),
        ('state', StateFilter),
    ]

    def shipment_state(self, obj):
        return TransitState(obj.state).label.upper()

    def has_delete_permission(self, request, obj=None):
        return False

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


class HistoricalShipmentAdmin(BaseModelHistory, ShipmentAdmin):
    readonly_fields = [field.name for field in Shipment._meta.get_fields()]


class LocationAdmin(BaseModelHistory):
    fieldsets = [(None, {'fields': [field.name for field in Location._meta.local_fields]})]

    readonly_fields = [field.name for field in Location._meta.get_fields()]

    search_fields = ('id', 'name__contains', )
