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

from django.contrib.gis.db.models import GeometryField
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from shipchain_common.utils import AliasField, random_id

from .shipment import Device, Shipment


class TrackingData(models.Model):
    id = models.CharField(primary_key=True, default=random_id, max_length=36)
    created_at = models.DateTimeField(auto_now_add=True)
    device = models.ForeignKey(Device, on_delete=models.DO_NOTHING)
    shipment = models.ForeignKey(Shipment, on_delete=models.CASCADE)
    latitude = models.FloatField(max_length=36)
    longitude = models.FloatField(max_length=36)
    altitude = models.FloatField(max_length=36, null=True, blank=True)
    source = models.CharField(max_length=36)
    uncertainty = models.IntegerField(validators=[MinValueValidator(0), MaxValueValidator(100)], null=True, blank=True)
    speed = models.FloatField(validators=[MinValueValidator(0)], null=True, blank=True)
    timestamp = models.DateTimeField()
    time = AliasField(db_column='timestamp')
    version = models.CharField(max_length=36)
    point = GeometryField()

    class Meta:
        ordering = ('timestamp',)
