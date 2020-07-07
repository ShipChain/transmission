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

from django.db import models
from shipchain_common.utils import random_id

from apps.shipments.models import Device, TransitState

LOG = logging.getLogger('transmission')


class Route(models.Model):
    id = models.CharField(primary_key=True, default=random_id, max_length=36)
    updated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)
    owner_id = models.UUIDField(null=False)

    name = models.CharField(max_length=64, null=True, blank=True)
    driver_id = models.UUIDField(null=True)
    device = models.OneToOneField(Device, on_delete=models.PROTECT, null=True)

    class Meta:
        ordering = ('created_at',)

    def get_next_leg_sequence(self):
        last_leg = self.routeleg_set.all().order_by('sequence').last()
        return (last_leg.sequence + 1) if last_leg else 1

    def can_disassociate_device(self):
        if not self.device:
            return True

        if self.routeleg_set.filter(shipment__state=TransitState.IN_TRANSIT.value).exists():
            return False

        return True
