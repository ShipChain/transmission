import json

from pygments import highlight
from pygments.lexers import JsonLexer
from pygments.formatters import HtmlFormatter

from django.contrib import admin
from django.contrib.contenttypes.models import ContentType
from django.utils.html import format_html

from apps.admin import admin_change_url
from .models import AsyncJob, JobState, AsyncAction, Message


class SafeJson(str):
    def __html__(self):
        return self


def pretty_json_print(field):
    response = json.dumps(field, sort_keys=True, indent=2)

    # Get the Pygments formatter
    formatter = HtmlFormatter(style='colorful')

    # Highlight the data
    response = highlight(response, JsonLexer(), formatter)

    # Get the stylesheet
    style = "<style>" + formatter.get_style_defs() + "</style><br>"

    # Safe the output
    return SafeJson(style + response)


def retry_attempt(async_job_admin, request, queryset):
    for job in queryset:
        job.state = JobState.PENDING
        job.save()
        job.fire(delay=job.delay)


class MessageInlineTab(admin.TabularInline):
    model = Message

    exclude = (
        'body',
    )

    readonly_fields = (
        'created_at',
        'body_display',
    )

    def body_display(self, obj):
        return pretty_json_print(obj.body)

    body_display.short_description = "Body"

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class AsyncActionInlineTab(admin.TabularInline):
    model = AsyncAction

    readonly_fields = (
        'created_at',
    )

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class AsyncJobAdmin(admin.ModelAdmin):
    actions = [retry_attempt]

    exclude = (
        'parameters',
    )

    list_display = (
        'id',
        'shipment_display',
        'state',
        'last_try',
        'created_at',
        'method_display',
        'actions_display',
    )

    list_filter = (
        'state',
        'last_try',
        'created_at',
    )

    readonly_fields = (
        'id',
        'shipment_display',
        'parameters_display',
        'state',
        'wallet_lock_token',
        'last_try',
        'delay',
    )

    inlines = [
        AsyncActionInlineTab,
        MessageInlineTab,
    ]

    search_fields = [
        'id',
    ]

    def shipment_display(self, obj):
        shipment = obj.listeners.filter(Model='shipments.Shipment').first()
        url = admin_change_url(shipment)
        return format_html(
            '<a href="{}">{}</a>',
            url,
            shipment.id if shipment else ''
        )

    shipment_display.short_description = "Shipment"

    def parameters_display(self, obj):
        return pretty_json_print(obj.parameters)

    parameters_display.short_description = "Parameters"

    def method_display(self, obj):
        try:
            params = obj.parameters
            return params['rpc_method']
        except KeyError:
            pass
        return "??"

    method_display.short_description = "Method"

    def actions_display(self, obj):
        trim_length = 22
        action_list = ", ".join([
            str(action.action_type) for action in obj.actions.all()
        ])[:trim_length]
        return action_list + '...' if len(action_list) == trim_length else action_list

    actions_display.short_description = "Actions"

    def get_search_results(self, request, queryset, search_term):
        queryset, use_distinct = super().get_search_results(request, queryset, search_term)
        queryset |= self.model.objects.filter(
            joblistener__listener_type=ContentType.objects.get(app_label="shipments", model="shipment").id,
            joblistener__listener_id__contains=search_term
        )
        return queryset, use_distinct

    def get_actions(self, request):
        actions = super().get_actions(request)
        if 'delete_selected' in actions:
            del actions['delete_selected']
        return actions

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


admin.site.register(AsyncJob, AsyncJobAdmin)
