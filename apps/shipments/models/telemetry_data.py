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
from shipchain_common.utils import random_id

from .shipment import Device, Shipment


class TelemetryData(models.Model):
    id = models.CharField(primary_key=True, default=random_id, max_length=36)
    created_at = models.DateTimeField(auto_now_add=True)

    device = models.ForeignKey(Device, on_delete=models.DO_NOTHING)
    shipment = models.ForeignKey(Shipment, on_delete=models.CASCADE)

    timestamp = models.DateTimeField(db_index=True)
    hardware_id = models.CharField(max_length=255)
    sensor_id = models.CharField(max_length=36)
    value = models.FloatField()
    version = models.CharField(max_length=36)

    class Meta:
        ordering = ('timestamp',)
