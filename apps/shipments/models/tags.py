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

import uuid

from django.contrib.postgres.fields import HStoreField
from django.contrib.postgres.validators import KeysValidator
from django.db import models

from .shipment import Shipment


class ShipmentTag(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=25, null=False)

    definition = HStoreField(validators=[KeysValidator(keys=['type', 'value'], strict=True)])

    user_id = models.UUIDField(null=False)

    shipment = models.ForeignKey(Shipment, on_delete=models.CASCADE, null=False)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('-created_at', )
