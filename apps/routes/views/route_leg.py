"""
Copyright 2020 ShipChain, Inc.

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

from shipchain_common.mixins import mixins as cgvs_mixins
from shipchain_common.viewsets import ConfigurableGenericViewSet, ActionConfiguration

from apps.routes.models import RouteLeg
from apps.routes.serializers import RouteLegCreateSerializer, RouteLegInfoSerializer

LOG = logging.getLogger('transmission')


class RouteLegViewSet(cgvs_mixins.CreateModelMixin,
                      cgvs_mixins.DestroyModelMixin,
                      ConfigurableGenericViewSet):

    queryset = RouteLeg.objects.all()
    serializer_class = RouteLegInfoSerializer

    configuration = {
        'create': ActionConfiguration(
            request_serializer=RouteLegCreateSerializer,
            response_serializer=RouteLegInfoSerializer,
        )
    }
