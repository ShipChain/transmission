from django.contrib import admin

from apps.admin import object_detail_admin_link
from apps.routes.models import RouteLeg
from apps.shipments.models import TransitState


class RouteLegAdmin(admin.ModelAdmin):
    model = RouteLeg
    can_delete = True

    exclude = (
        'route',
        'shipment',
    )

    readonly_fields = (
        'id',
        'route_link',
        'shipment_link',
        '_order',
        'status_display',
    )

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        if obj and obj.route.routeleg_set.filter(shipment__state__gt=TransitState.AWAITING_PICKUP.value).exists():
            return False
        return True

    def route_link(self, obj):
        return object_detail_admin_link(obj.route)
    route_link.short_description = 'Route'

    def shipment_link(self, obj):
        return object_detail_admin_link(obj.shipment)
    shipment_link.short_description = 'Shipment'

    def status_display(self, obj):
        return TransitState(obj.shipment.state).label.upper()
    status_display.short_description = 'Status'
