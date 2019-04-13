from django import http
from django.contrib import admin
from django.contrib.contenttypes.admin import GenericTabularInline
from django.utils.html import format_html
from django.contrib.admin import helpers
from django.contrib.admin.utils import unquote
from django.contrib.contenttypes.models import ContentType
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils.encoding import force_text
from django.utils.html import mark_safe
from django.utils.text import capfirst
from django.utils.translation import ugettext as _

from simple_history.admin import SimpleHistoryAdmin, USER_NATURAL_KEY, SIMPLE_HISTORY_EDIT

from apps.admin import admin_change_url
from apps.shipments.models import Shipment, Location, ShallowUser


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


class BaseModelHistory(SimpleHistoryAdmin):
    fieldsets = (
        (None, {
            'classes': ('extrapretty'),
            'fields': (
                'id',
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

    def history_view(self, request, object_id, extra_context=None):     # pylint:disable=too-many-locals
        request.current_app = self.admin_site.name
        model = self.model
        opts = model._meta
        app_label = opts.app_label
        pk_name = opts.pk.attname
        history = getattr(model, model._meta.simple_history_manager_attribute)
        object_id = unquote(object_id)
        action_list = history.filter(**{pk_name: object_id})
        if not isinstance(history.model.history_user, property):
            # Only select_related when history_user is a ForeignKey (not a property)
            action_list = action_list.select_related("history_user")
        history_list_display = getattr(self, "history_list_display", [])
        # If no history was found, see whether this object even exists.
        try:
            obj = self.get_queryset(request).get(**{pk_name: object_id})
        except model.DoesNotExist:
            try:
                obj = action_list.latest("history_date").instance
            except action_list.model.DoesNotExist:
                raise http.Http404

        if not self.has_change_permission(request, obj):
            # We override this behavior for the moment
            # raise PermissionDenied
            pass

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

        # We override this behavior for the moment
        if not self.has_change_permission(request, obj):
            # raise PermissionDenied
            pass

        change_history = bool(SIMPLE_HISTORY_EDIT)

        if "_change_history" in request.POST and SIMPLE_HISTORY_EDIT:
            obj = obj.history.get(pk=version_id).instance

        formsets = []
        form_class = self.get_form(request, obj)
        if request.method == "POST":
            form = form_class(request.POST, request.FILES, instance=obj)
            if form.is_valid():
                new_object = self.save_form(request, form, change=True)
                self.save_model(request, new_object, form, change=True)
                form.save_m2m()

                self.log_change(
                    request,
                    new_object,
                    self.construct_change_message(request, form, formsets),
                )
                return self.response_change(request, new_object)

        else:
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
            "change": True,
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


class HistoricalShipmentAdmin(BaseModelHistory, ShipmentAdmin):
    pass


class ShallowUserAdmin(admin.ModelAdmin):

    def has_delete_permission(self, request, obj=None):
        return False

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


EXCLUDED_FIELDS = ('shipment_to', 'shipment_from', 'shipment_dest', 'shipment_bill', 'shipment_bill', 'updated_at',
                   'created_at')


class LocationAdmin(BaseModelHistory):
    fieldsets = [(None, {'fields': [field.name for field in Location._meta.get_fields() if
                                    field.name not in EXCLUDED_FIELDS]})]

    def has_delete_permission(self, request, obj=None):
        return False

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


admin.site.register(Shipment, ShipmentAdmin)

admin.site.unregister(Shipment)

admin.site.register(Shipment, HistoricalShipmentAdmin)

admin.site.register(Location, LocationAdmin)

admin.site.register(ShallowUser, ShallowUserAdmin)
