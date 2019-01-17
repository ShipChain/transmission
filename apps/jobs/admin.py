from django.contrib import admin
from guardian.admin import GuardedModelAdmin

from .models import AsyncJob


def retry_attempt(JobAdmin, request, queryset):
    for job in queryset:
        job.fire(delay=job.delay)


class JobAdmin(GuardedModelAdmin):
    actions = [retry_attempt]

    list_display = (
        'state',
        'last_try',
    )

    list_filter = (
        'state',
        'last_try',
    )

    readonly_fields = (
        'id',
        'state',
        'wallet_lock_token',
        'last_try',
    )

    def get_actions(self, request):
        actions = super().get_actions(request)
        if 'delete_selected' in actions:
            del actions['delete_selected']
        return actions

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


admin.site.register(AsyncJob, JobAdmin)
