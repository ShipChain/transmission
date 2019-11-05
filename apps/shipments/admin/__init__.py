from django.contrib import admin

from apps.shipments.models import Shipment, Location

from .shipment import HistoricalShipmentAdmin, LocationAdmin


admin.site.register(Shipment, HistoricalShipmentAdmin)
admin.site.register(Location, LocationAdmin)
