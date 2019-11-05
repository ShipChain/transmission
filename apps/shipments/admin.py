from django import http
from django.contrib import admin
from django.contrib.admin import helpers, SimpleListFilter
from django.contrib.admin.utils import unquote
from django.contrib.contenttypes.models import ContentType
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils.encoding import force_text
from django.utils.html import format_html
from django.utils.html import mark_safe
from django.utils.text import capfirst
from django.utils.translation import ugettext as _
from simple_history.admin import SimpleHistoryAdmin, USER_NATURAL_KEY, SIMPLE_HISTORY_EDIT
from enumfields.admin import EnumFieldListFilter

from apps.shipments.models import Shipment, Location, TransitState
from apps.jobs.models import AsyncJob


class StateFilter(SimpleListFilter):
    title = 'State'
    parameter_name = 'state'

    def lookups(self, request, model_admin):
        return [
            (10, 'AWAITING_PICKUP'),
            (20, 'IN_TRANSIT'),
            (30, 'AWAITING_DELIVERY'),
            (40, 'DELIVERED')
        ]

    def queryset(self, request, queryset):
        return queryset.filter(state=self.value())

    # def expected_parameters(self):
    #     return [self.parameter_name]


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
        # ('state', StateFilter),
    ]

    def shipment_state(self, obj):
        return TransitState(obj.state).label.upper()

    def has_delete_permission(self, request, obj=None):
        return False

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


class BaseModelHistory(SimpleHistoryAdmin):

    def history_view(self, request, object_id, extra_context=None):     # pylint:disable=too-many-locals
        request.current_app = self.admin_site.name
        model = self.model
        opts = model._meta
        app_label = opts.app_label
        pk_name = opts.pk.attname
        history = getattr(model, model._meta.simple_history_manager_attribute)
        object_id = unquote(object_id)
        action_list = history.filter(**{pk_name: object_id})

        history_list_display = getattr(self, "history_list_display", [])
        # If no history was found, see whether this object even exists.
        try:
            obj = self.get_queryset(request).get(**{pk_name: object_id})
        except model.DoesNotExist:
            try:
                obj = action_list.latest("history_date").instance
            except action_list.model.DoesNotExist:
                raise http.Http404

        for history_list_entry in history_list_display:
            value_for_entry = getattr(self, history_list_entry, None)
            if value_for_entry and callable(value_for_entry):
                for list_entry in action_list:
                    setattr(list_entry, history_list_entry, value_for_entry(list_entry))

        content_type = ContentType.objects.get_by_natural_key(*USER_NATURAL_KEY)
        admin_user_view = "admin:%s_%s_change" % (
            content_type.app_label,
            content_type.model,
        )
        context = {
            "title": _("Change history: %s") % force_text(obj),
            "action_list": action_list,
            "module_name": capfirst(force_text(opts.verbose_name_plural)),
            "object": obj,
            "root_path": getattr(self.admin_site, "root_path", None),
            "app_label": app_label,
            "opts": opts,
            "admin_user_view": admin_user_view,
            "history_list_display": history_list_display,
        }
        context.update(self.admin_site.each_context(request))
        context.update(extra_context or {})
        extra_kwargs = {}
        return render(request, self.object_history_template, context, **extra_kwargs)

    def history_form_view(self, request, object_id, version_id, extra_context=None):    # pylint:disable=too-many-locals
        request.current_app = self.admin_site.name
        original_opts = self.model._meta
        model = getattr(
            self.model, self.model._meta.simple_history_manager_attribute
        ).model
        obj = get_object_or_404(
            model, **{original_opts.pk.attname: object_id, "history_id": version_id}
        ).instance
        obj._state.adding = False   # pylint:disable=protected-access

        change_history = SIMPLE_HISTORY_EDIT
        formsets = []
        form_class = self.get_form(request, obj)

        form = form_class(instance=obj)

        admin_form = helpers.AdminForm(
            form,
            self.fieldsets,
            self.prepopulated_fields,
            self.get_readonly_fields(request, obj),
            model_admin=self,
        )

        model_name = original_opts.model_name
        url_triplet = self.admin_site.name, original_opts.app_label, model_name
        context = {
            "title": _("Revert %s") % force_text(obj),
            "adminform": admin_form,
            "object_id": object_id,
            "original": obj,
            "is_popup": False,
            "media": mark_safe(self.media + admin_form.media),
            "errors": helpers.AdminErrorList(form, formsets),
            "app_label": original_opts.app_label,
            "original_opts": original_opts,
            "changelist_url": reverse("%s:%s_%s_changelist" % url_triplet),
            "change_url": reverse("%s:%s_%s_change" % url_triplet, args=(obj.pk,)),
            "history_url": reverse("%s:%s_%s_history" % url_triplet, args=(obj.pk,)),
            "change_history": change_history,
            # Context variables copied from render_change_form
            "add": False,
            "change": False,
            "has_add_permission": self.has_add_permission(request),
            "has_change_permission": self.has_change_permission(request, obj),
            "has_delete_permission": self.has_delete_permission(request, obj),
            "has_file_field": True,
            "has_absolute_url": False,
            "form_url": "",
            "opts": model._meta,
            "content_type_id": ContentType.objects.get_for_model(self.model).id,
            "save_as": self.save_as,
            "save_on_top": self.save_on_top,
            "root_path": getattr(self.admin_site, "root_path", None),
        }
        context.update(self.admin_site.each_context(request))
        context.update(extra_context or {})
        extra_kwargs = {}
        return render(
            request, self.object_history_form_template, context, **extra_kwargs
        )

    def has_delete_permission(self, request, obj=None):
        return False

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


class HistoricalShipmentAdmin(BaseModelHistory, ShipmentAdmin):
    readonly_fields = [field.name for field in Shipment._meta.get_fields()]
    # list_filter = [
    #     ('created_at', admin.DateFieldListFilter),
    #     ('delayed', admin.BooleanFieldListFilter),
    #     ('state', StateFilter),
    #     # ('contract_version', admin.ChoicesFieldListFilter)
    # ]


class LocationAdmin(BaseModelHistory):
    fieldsets = [(None, {'fields': [field.name for field in Location._meta.local_fields]})]

    readonly_fields = [field.name for field in Location._meta.get_fields()]

    search_fields = ('id', 'name__contains', )


admin.site.register(Shipment, HistoricalShipmentAdmin)

admin.site.register(Location, LocationAdmin)
