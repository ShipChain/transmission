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
from django.forms.fields import MultipleChoiceField
from django_filters import rest_framework as filters
from rest_framework_json_api.serializers import ValidationError
from shipchain_common.filters import filter_enum

from apps.routes.models import RouteTelemetryData
from apps.shipments.models import Shipment, TransitState, TelemetryData, TrackingData

SHIPMENT_STATE_CHOICES = tuple((m.name, m.value, ) for m in TransitState)


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
        queryset = queryset.filter(state__in=enum_values)
    else:
        queryset = queryset.filter(shipment__state__in=enum_values)

    return queryset


class CaseInsensitiveMultipleChoiceField(MultipleChoiceField):
    def valid_value(self, value):
        value = value.upper()
        return super().valid_value(value)


class CustomMultipleChoiceFilter(filters.MultipleChoiceFilter):
    field_class = CaseInsensitiveMultipleChoiceField


class ShipmentFilter(filters.filterset.FilterSet):
    has_ship_from_location = filters.BooleanFilter(field_name='ship_from_location', lookup_expr='isnull', exclude=True)
    has_ship_to_location = filters.BooleanFilter(field_name='ship_to_location', lookup_expr='isnull', exclude=True)
    has_final_destination_location = filters.BooleanFilter(
        field_name='final_destination_location', lookup_expr='isnull', exclude=True)
    has_quickadd_tracking = filters.BooleanFilter(field_name='quickadd_tracking', lookup_expr='isnull', exclude=True)
    state = CustomMultipleChoiceFilter(method=filter_state, choices=SHIPMENT_STATE_CHOICES)
    exception = filters.CharFilter(method=filter_enum)
    gtx_validation = filters.CharFilter(method=filter_enum)
    assignee_id = filters.UUIDFilter(field_name='assignee_id')

    # Tag filter fields
    tag_type = filters.CharFilter(field_name='shipment_tags__tag_type', lookup_expr='icontains', distinct=True)
    tag_value = filters.CharFilter(field_name='shipment_tags__tag_value', lookup_expr='icontains', distinct=True)

    class Meta:
        model = Shipment
        fields = (
            'mode_of_transport_code',
            'ship_from_location__name',
            'ship_from_location__city',
            'ship_from_location__address_1',
            'ship_from_location__postal_code',
            'ship_from_location__country',
            'ship_to_location__name',
            'ship_to_location__city',
            'ship_to_location__state',
            'ship_to_location__address_1',
            'ship_to_location__postal_code',
            'ship_to_location__country',
            'final_destination_location__name',
            'final_destination_location__city',
            'ship_from_location',
            'final_destination_location__state',
            'final_destination_location__address_1',
            'ship_to_location',
            'final_destination_location__postal_code',
            'final_destination_location__country',
            'final_destination_location',
            'ship_from_location__state',
            'state',
            'delayed',
            'asset_physical_id',
            'asset_custodian_id',
            'quickadd_tracking',
            'carrier_abbv',
        )


class ShipmentOverviewFilter(ShipmentFilter):
    shipment__has_ship_from_location = filters.BooleanFilter(field_name='shipment__ship_from_location',
                                                             lookup_expr='isnull', exclude=True)
    shipment__has_ship_to_location = filters.BooleanFilter(field_name='shipment__ship_to_location',
                                                           lookup_expr='isnull', exclude=True)
    shipment__has_final_destination_location = filters.BooleanFilter(
        field_name='shipment__final_destination_location', lookup_expr='isnull', exclude=True)
    shipment__state = CustomMultipleChoiceFilter(field_name='shipment__state', method=filter_state,
                                                 choices=SHIPMENT_STATE_CHOICES)
    shipment__exception = filters.CharFilter(field_name='shipment__exception', method=filter_enum)
    shipment__assignee_id = filters.UUIDFilter(field_name='shipment__assignee_id')
    has_quickadd_tracking = filters.BooleanFilter(field_name='shipment__quickadd_tracking', lookup_expr='isnull',
                                                  exclude=True)

    # Tag filter fields
    shipment__tag_type = filters.CharFilter(field_name='shipment__shipment_tags__tag_type', lookup_expr='icontains',
                                            distinct=True)
    shipment__tag_value = filters.CharFilter(field_name='shipment__shipment_tags__tag_value', lookup_expr='icontains',
                                             distinct=True)

    class Meta:
        model = TrackingData
        fields = tuple([f'shipment__{field}' for field in ShipmentFilter.Meta.fields])


SHIPMENT_SEARCH_FIELDS = (
    'shippers_reference',
    'forwarders_reference',
    'ship_from_location__name',
    'ship_from_location__city',
    'ship_from_location__address_1',
    'ship_from_location__postal_code',
    'ship_from_location__country',
    'ship_from_location__state',
    'ship_from_location__contact_name',
    'ship_from_location__contact_email',
    'ship_to_location__name',
    'ship_to_location__city',
    'ship_to_location__address_1',
    'ship_to_location__postal_code',
    'ship_to_location__country',
    'ship_to_location__state',
    'ship_to_location__contact_name',
    'ship_to_location__contact_email',
    'final_destination_location__name',
    'final_destination_location__city',
    'final_destination_location__address_1',
    'final_destination_location__postal_code',
    'final_destination_location__country',
    'final_destination_location__state',
    'final_destination_location__contact_name',
    'final_destination_location__contact_email',
    'shipment_tags__tag_type',
    'shipment_tags__tag_value',
    'quickadd_tracking',
    'customer_fields',
    'pk'
)

SHIPMENT_ORDERING_FIELDS = (
    'updated_at',
    'created_at',
    'pickup_est',
    'delivery_est'
)


TELEMETRY_FILTER_FIELDS = (
    'sensor_id',
    'hardware_id',
    'before',
    'after',
)


class TelemetryFilter(filters.filterset.FilterSet):
    after = filters.IsoDateTimeFilter(field_name="timestamp", lookup_expr='gte')
    before = filters.IsoDateTimeFilter(field_name="timestamp", lookup_expr='lte')

    class Meta:
        model = TelemetryData
        fields = TELEMETRY_FILTER_FIELDS


class RouteTelemetryFilter(filters.filterset.FilterSet):
    after = filters.IsoDateTimeFilter(field_name="timestamp", lookup_expr='gte')
    before = filters.IsoDateTimeFilter(field_name="timestamp", lookup_expr='lte')

    class Meta:
        model = RouteTelemetryData
        fields = TELEMETRY_FILTER_FIELDS
