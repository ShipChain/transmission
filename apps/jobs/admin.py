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

from apps.admin import pretty_json_print, shipment_admin_link
from .models import AsyncJob, JobState, AsyncAction, Message


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

    list_per_page = settings.ADMIN_PAGE_SIZE

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

    list_filter = [
        ('last_try', DateRangeFilter),
        ('created_at', DateRangeFilter),
        ('state', EnumFieldListFilter)
    ]

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
        return shipment_admin_link(obj.shipment)

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
        searched_queryset, use_distinct = super().get_search_results(request, queryset, search_term)

        shipment_queryset = queryset.filter(
            shipment__id__contains=search_term
        )

        queryset = searched_queryset | shipment_queryset

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
