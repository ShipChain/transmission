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

from .shipment import Device, Shipment
from ...abstract_models import AbstractTrackingData


class TrackingData(AbstractTrackingData):
    device = models.ForeignKey(Device, on_delete=models.DO_NOTHING)
    shipment = models.ForeignKey(Shipment, on_delete=models.CASCADE)
