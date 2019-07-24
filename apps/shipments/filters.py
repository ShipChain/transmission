from django_filters import rest_framework as filters

from .models import Shipment


class ShipmentFilter(filters.filterset.FilterSet):
    has_ship_from_location = filters.BooleanFilter(field_name='ship_from_location', lookup_expr='isnull', exclude=True)
    has_ship_to_location = filters.BooleanFilter(field_name='ship_to_location', lookup_expr='isnull', exclude=True)
    has_final_destination_location = filters.BooleanFilter(
        field_name='final_destination_location', lookup_expr='isnull', exclude=True)

    class Meta:
        model = Shipment
        fields = ['mode_of_transport_code', 'ship_from_location__name', 'ship_from_location__city',
                  'ship_from_location__address_1', 'ship_from_location__postal_code', 'ship_from_location__country',
                  'ship_to_location__name', 'ship_to_location__city', 'ship_to_location__state',
                  'ship_to_location__address_1', 'ship_to_location__postal_code', 'ship_to_location__country',
                  'final_destination_location__name', 'final_destination_location__city', 'ship_from_location',
                  'final_destination_location__state', 'final_destination_location__address_1', 'ship_to_location',
                  'final_destination_location__postal_code', 'final_destination_location__country',
                  'final_destination_location', 'ship_from_location__state', 'state', 'exception', 'delayed']


class HistoricalShipmentFilter(filters.filterset.FilterSet):
    history_date__gte = filters.IsoDateTimeFilter(field_name='history_date', lookup_expr='gte')
    history_date__lte = filters.IsoDateTimeFilter(field_name='history_date', lookup_expr='lte')

    class Meta:
        model = Shipment.history.model
        fields = ('history_date', 'updated_at', )
