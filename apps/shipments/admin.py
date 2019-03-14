from django.contrib import admin

from apps.shipments.models import Shipment


class ShipmentAdmin(admin.ModelAdmin):
    # Read Only admin page until this feature is worked

    def has_delete_permission(self, request, obj=None):
        return False

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


admin.site.register(Shipment, ShipmentAdmin)
