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

from apps.routes.models.route import Route
from apps.shipments.models import Shipment

LOG = logging.getLogger('transmission')


class RouteLeg(models.Model):
    id = models.CharField(primary_key=True, default=random_id, max_length=36)
    updated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    route = models.ForeignKey(Route, on_delete=models.CASCADE)
    shipment = models.OneToOneField(Shipment, on_delete=models.CASCADE)
    sequence = models.IntegerField(null=False, blank=False)

    class Meta:
        ordering = ('route', 'sequence')
