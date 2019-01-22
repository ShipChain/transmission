from django.contrib import admin

from .models import AsyncJob


def retry_attempt(async_job_admin, request, queryset):
    for job in queryset:
        job.fire(delay=job.delay)


class AsyncJobAdmin(admin.ModelAdmin):
    actions = [retry_attempt]

    list_display = (
        'state',
        'last_try',
        'created_at',
        'updated_at',
    )

    list_filter = (
        'state',
        'last_try',
        'created_at',
        'updated_at',
    )

    readonly_fields = (
        'id',
        'state',
        'wallet_lock_token',
        'last_try',
        'delay',
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


admin.site.register(AsyncJob, AsyncJobAdmin)
