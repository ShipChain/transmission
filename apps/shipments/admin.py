from django.contrib import admin
from django.contrib.contenttypes.admin import GenericTabularInline
from django.utils.html import format_html

from apps.admin import admin_change_url
from apps.shipments.models import Shipment


class AsyncJobInlineTab(GenericTabularInline):
    model = Shipment.asyncjob_set.through
    ct_field = 'listener_type'
    ct_fk_field = 'listener_id'

    exclude = (
        'async_job',
    )

    readonly_fields = (
        'async_job_id',
        'async_job_state',
        'async_job_method',
        'async_job_created_at',
        'async_job_last_try',
    )

    def async_job_id(self, obj):
        url = admin_change_url(obj.async_job)
        return format_html(
            '<a href="{}">{}</a>',
            url,
            obj.async_job.id
        )

    def async_job_state(self, obj):
        return obj.async_job.state

    def async_job_method(self, obj):
        try:
            params = obj.async_job.parameters
            return params['rpc_method']
        except KeyError:
            pass
        return "??"

    def async_job_created_at(self, obj):
        return obj.async_job.created_at

    def async_job_last_try(self, obj):
        return obj.async_job.last_try

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
    'job_listeners',
    'eth_listeners',
    'asyncjob_set_relation',
    'ethaction_set_relation',
]


class ShipmentAdmin(admin.ModelAdmin):
    # Read Only admin page until this feature is worked

    fieldsets = (
        (None, {
            'classes': ('extrapretty'),
            'fields': (
                'id',
                ('updated_at', 'created_at',),
                ('owner_id', 'updated_by',),
                ('shipper_wallet_id', 'carrier_wallet_id', 'moderator_wallet_id',),
                ('storage_credentials_id', 'vault_id',),
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

    def has_delete_permission(self, request, obj=None):
        return False

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


admin.site.register(Shipment, ShipmentAdmin)
