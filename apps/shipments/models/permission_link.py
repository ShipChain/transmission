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
from datetime import datetime, timezone

from django.db import models
from shipchain_common.utils import random_id

from .shipment import Shipment

LOG = logging.getLogger('transmission')


class PermissionLink(models.Model):
    id = models.CharField(primary_key=True, default=random_id, max_length=36)
    expiration_date = models.DateTimeField(blank=True, null=True)
    name = models.CharField(null=False, max_length=255)
    shipment = models.ForeignKey(Shipment, on_delete=models.CASCADE, null=False)
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def is_valid(self):
        if not self.expiration_date:
            return True
        return datetime.now(timezone.utc) < self.expiration_date
