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

import logging

from collections import OrderedDict
from django.conf import settings
from django.db.models import Q
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, permissions
from rest_framework.generics import ListAPIView
from rest_framework_gis.filters import InBBoxFilter
from rest_framework_json_api import utils
from rest_framework_json_api import views as jsapi_views
from rest_framework_json_api.renderers import JSONRenderer

from apps.permissions import get_owner_id
from ..serializers import QueryParamsSerializer, TrackingOverviewSerializer
from ..models import TrackingData, PermissionLink
from ..filters import ShipmentOverviewFilter, SHIPMENT_SEARCH_FIELDS, SHIPMENT_ORDERING_FIELDS

LOG = logging.getLogger('transmission')


class JSONAPIGeojsonRenderer(JSONRenderer):
    # Class that allows a nested serializer to be specified in attributes. For rendering `point` as GeoJSON.
    # (This allows us to render TrackingOverviewGeojsonSerializer as a JSON API attribute on TrackingOverviewSerializer)

    # Exact copy of django-rest-framework-json-api JSONRenderer with the following lines removed from extract_attributes
    # https://github.com/django-json-api/django-rest-framework-json-api/blob/9d42d9b7018b08e2df399e598d75f057676b3870/re
    # st_framework_json_api/renderers.py#L62-L66
    @classmethod
    def extract_attributes(cls, fields, resource):
        """
        Builds the `attributes` object of the JSON API resource object.
        """
        data = OrderedDict()
        for field_name, _ in iter(fields.items()):
            # ID is always provided in the root of JSON API so remove it from attributes
            if field_name == 'id':
                continue
            # don't output a key for write only fields
            if fields[field_name].write_only:
                continue

            # Skip read_only attribute fields when `resource` is an empty
            # serializer. Prevents the "Raw Data" form of the browsable API
            # from rendering `"foo": null` for read only fields
            try:
                resource[field_name]
            except KeyError:
                if fields[field_name].read_only:
                    continue

            data.update({
                field_name: resource.get(field_name)
            })

        return utils.format_field_names(data)


class ShipmentOverviewListView(jsapi_views.PreloadIncludesMixin,
                               jsapi_views.AutoPrefetchMixin,
                               jsapi_views.RelatedMixin,
                               ListAPIView):
    queryset = TrackingData.objects.all()
    select_for_includes = {
        '__all__': ['shipment']
    }

    serializer_class = TrackingOverviewSerializer
    permission_classes = (permissions.IsAuthenticated,)
    renderer_classes = (JSONAPIGeojsonRenderer,)

    filter_backends = (InBBoxFilter, filters.SearchFilter, filters.OrderingFilter, DjangoFilterBackend,)
    bbox_filter_field = 'point'
    search_fields = tuple([f'shipment__{field}' for field in SHIPMENT_SEARCH_FIELDS])
    ordering_fields = tuple([f'shipment__{field}' for field in SHIPMENT_ORDERING_FIELDS])
    filterset_class = ShipmentOverviewFilter

    def dispatch(self, request, *args, **kwargs):
        # pylint:disable=protected-access
        request.GET._mutable = True  # Make query_params mutable
        for param in dict(request.GET):
            # Prepend non-trackingdata search/filter/order query params with 'shipment__' to properly query relation
            if param not in ('search', 'in_bbox', 'ordering') and request.GET.getlist(param):
                request.GET.setlist(f'shipment__{param}', request.GET.pop(param))
            elif param in ('ordering',) and request.GET.getlist(param):
                request.GET.setlist(param,
                                    [f'-shipment__{ship_ordering.replace("-", "")}' if '-' in ship_ordering else
                                     f'shipment__{ship_ordering}' for ship_ordering in request.GET.getlist(param)])
        request.GET._mutable = False  # Make query_params immutable
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self, *args, **kwargs):
        queryset = super().get_queryset(*args, **kwargs)

        # Get latest tracking point for each shipment
        queryset = queryset.filter(id__in=TrackingData.objects
                                   .order_by('shipment_id', '-timestamp')
                                   .distinct('shipment_id')
                                   .values('id'))

        if settings.PROFILES_ENABLED:
            queryset_filter = Q(shipment__owner_id=get_owner_id(self.request))
            permission_link_id = self.request.query_params.get('shipment__permission_link')
            permission_link = PermissionLink.objects.filter(id=permission_link_id).first()
            if permission_link and permission_link.is_valid:
                queryset_filter = queryset_filter | Q(shipment_id=permission_link.shipment_id)

            # Filter by owner or permission link's shipment id
            queryset = queryset.filter(queryset_filter)

        return queryset

    def get(self, request, *args, **kwargs):
        # Validate query parameters with a request serializer
        param_serializer = QueryParamsSerializer(data=request.query_params)
        param_serializer.is_valid(raise_exception=True)

        return super().get(request, *args, **kwargs)
