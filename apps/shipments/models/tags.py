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
from django.core.validators import RegexValidator
from django.db import models

from .shipment import Shipment


class ShipmentTag(models.Model):
    tag_field_regex_validator = RegexValidator(regex=r'^\S*$', message='Space(s) not allowed in this field')

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    tag_type = models.CharField(max_length=50, null=False, validators=[tag_field_regex_validator])
    tag_value = models.CharField(max_length=50, null=False, validators=[tag_field_regex_validator])

    user_id = models.UUIDField(null=False)

    shipment = models.ForeignKey(Shipment, on_delete=models.CASCADE, null=False, related_name='shipment_tags')

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('-created_at', )
