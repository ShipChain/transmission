from django_filters import rest_framework as filters
from rest_framework_json_api.serializers import ValidationError
from shipchain_common.filters import filter_enum

from .models import Shipment, TransitState, TrackingData


MULTI_STATE_CHOICES = tuple((m.name.lower(), m.value, ) for m in TransitState) + \
                      tuple((m.name, m.value, ) for m in TransitState)


def filter_state(queryset, _, value):
    if not isinstance(value, list):
        value = [value]

    enum_values = []
    for item in value:
        try:
            enum_value = TransitState[item.upper()]
        except KeyError:
            raise ValidationError('Invalid shipment state supplied.')
        enum_values.append(enum_value.value)

    if issubclass(queryset.model, Shipment):
        queryset = queryset.filter(**{'state__in': enum_values})

    if issubclass(queryset.model, TrackingData):
        queryset = queryset.filter(**{'shipment__state__in': enum_values})

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


class ShipmentOverviewFilter(filters.filterset.FilterSet):
    has_ship_from_location = filters.BooleanFilter(
        field_name='shipment__ship_from_location', lookup_expr='isnull', exclude=True)
    has_ship_to_location = filters.BooleanFilter(
        field_name='shipment__ship_to_location', lookup_expr='isnull', exclude=True)
    has_final_destination_location = filters.BooleanFilter(
        field_name='shipment__final_destination_location', lookup_expr='isnull', exclude=True)
    state = filters.MultipleChoiceFilter(method=filter_state, field_name='shipment', choices=MULTI_STATE_CHOICES)
    exception = filters.CharFilter(method=filter_enum)

    class Meta:
        model = TrackingData
        fields = (
            'shipment__mode_of_transport_code',
            'shipment__ship_from_location__name',
            'shipment__ship_from_location__city',
            'shipment__ship_from_location__address_1',
            'shipment__ship_from_location__postal_code',
            'shipment__ship_from_location__country',
            'shipment__ship_to_location__name',
            'shipment__ship_to_location__city',
            'shipment__ship_to_location__state',
            'shipment__ship_to_location__address_1',
            'shipment__ship_to_location__postal_code',
            'shipment__ship_to_location__country',
            'shipment__final_destination_location__name',
            'shipment__final_destination_location__city',
            'shipment__ship_from_location',
            'shipment__final_destination_location__state',
            'shipment__final_destination_location__address_1',
            'shipment__ship_to_location',
            'shipment__final_destination_location__postal_code',
            'shipment__final_destination_location__country',
            'shipment__final_destination_location',
            'shipment__ship_from_location__state',
            'shipment__state',
            'shipment__delayed',
            'shipment__asset_physical_id',
            'shipment__asset_custodian_id'
        )


SHIPMENT_OVERVIEW_SEARCH_FIELDS = tuple(f'shipment__{shipment_field}' for shipment_field in SHIPMENT_SEARCH_FIELDS)
