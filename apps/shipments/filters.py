from django_filters import rest_framework as filters

from .models import Shipment


class ShipmentFilter(filters.filterset.FilterSet):
    has_ship_from_location = filters.BooleanFilter(field_name='ship_from_location', lookup_expr='isnull', exclude=True)
    has_ship_to_location = filters.BooleanFilter(field_name='ship_to_location', lookup_expr='isnull', exclude=True)
    has_final_destination_location = filters.BooleanFilter(
        field_name='final_destination_location', lookup_expr='isnull', exclude=True)

    class Meta:
        model = Shipment
        fields = ['mode', 'ship_from_location__name', 'ship_from_location__city', 'ship_from_location__state',
                  'ship_from_location__address_1', 'ship_from_location__postal_code', 'ship_from_location__country',
                  'ship_to_location__name', 'ship_to_location__city', 'ship_to_location__state',
                  'ship_to_location__address_1', 'ship_to_location__postal_code', 'ship_to_location__country',
                  'final_destination_location__name', 'final_destination_location__city', 'ship_from_location',
                  'final_destination_location__state', 'final_destination_location__address_1', 'ship_to_location',
                  'final_destination_location__postal_code', 'final_destination_location__country',
                  'final_destination_location']
