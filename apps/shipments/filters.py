from django_filters import rest_framework as filters
from rest_framework_json_api.serializers import ValidationError
from shipchain_common.filters import filter_enum

from .models import Shipment, TransitState


def filter_state(queryset, _, value):
    try:
        enum_value = TransitState[value.upper()]
    except KeyError:
        raise ValidationError('Invalid shipment state supplied.')

    queryset = queryset.filter(**{'state': enum_value.value})
    return queryset


class ShipmentFilter(filters.filterset.FilterSet):
    has_ship_from_location = filters.BooleanFilter(field_name='ship_from_location', lookup_expr='isnull', exclude=True)
    has_ship_to_location = filters.BooleanFilter(field_name='ship_to_location', lookup_expr='isnull', exclude=True)
    has_final_destination_location = filters.BooleanFilter(
        field_name='final_destination_location', lookup_expr='isnull', exclude=True)
    state = filters.CharFilter(method=filter_state)
    exception = filters.CharFilter(method=filter_enum)

    class Meta:
        model = Shipment
        fields = ['mode_of_transport_code', 'ship_from_location__name', 'ship_from_location__city',
                  'ship_from_location__address_1', 'ship_from_location__postal_code', 'ship_from_location__country',
                  'ship_to_location__name', 'ship_to_location__city', 'ship_to_location__state',
                  'ship_to_location__address_1', 'ship_to_location__postal_code', 'ship_to_location__country',
                  'final_destination_location__name', 'final_destination_location__city', 'ship_from_location',
                  'final_destination_location__state', 'final_destination_location__address_1', 'ship_to_location',
                  'final_destination_location__postal_code', 'final_destination_location__country',
                  'final_destination_location', 'ship_from_location__state', 'state', 'delayed',
                  'asset_physical_id', 'asset_custodian_id']


SHIPMENT_SEARCH_FIELDS = (
    'shippers_reference', 'forwarders_reference',
    'ship_from_location__name', 'ship_from_location__city', 'ship_from_location__address_1',
    'ship_from_location__postal_code', 'ship_from_location__country', 'ship_from_location__state',
    'ship_from_location__contact_name', 'ship_from_location__contact_email',
    'ship_to_location__name', 'ship_to_location__city', 'ship_to_location__address_1',
    'ship_to_location__postal_code', 'ship_to_location__country', 'ship_to_location__state',
    'ship_to_location__contact_name', 'ship_to_location__contact_email',
    'final_destination_location__name', 'final_destination_location__city', 'final_destination_location__address_1',
    'final_destination_location__postal_code', 'final_destination_location__country',
    'final_destination_location__state', 'final_destination_location__contact_name',
    'final_destination_location__contact_email',
)
