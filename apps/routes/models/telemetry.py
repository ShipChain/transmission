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
from django.db import models

from apps.abstract_models import AbstractTelemetryData
from apps.routes.models.route import Route
from apps.shipments.models import Device


class RouteTelemetryData(AbstractTelemetryData):
    device = models.ForeignKey(Device, on_delete=models.DO_NOTHING)
    route = models.ForeignKey(Route, on_delete=models.CASCADE)
