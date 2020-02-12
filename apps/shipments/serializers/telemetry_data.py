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

from apps.shipments.models import TelemetryData
from . import BaseDataToDbSerializer

LOG = logging.getLogger('transmission')


class TelemetryDataToDbSerializer(BaseDataToDbSerializer):
    """
    Serializer for tracking data to be cached in db
    """
    class Meta:
        model = TelemetryData
        exclude = ('device',)

    def create(self, validated_data):
        return TelemetryData.objects.create(**validated_data, **self.context)
