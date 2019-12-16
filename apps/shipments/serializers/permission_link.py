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

from datetime import datetime, timezone

from rest_framework import exceptions
from rest_framework_json_api import serializers

from apps.shipments.models import PermissionLink


class PermissionLinkSerializer(serializers.ModelSerializer):
    shipment_id = serializers.CharField(max_length=36, required=False)

    class Meta:
        model = PermissionLink
        fields = '__all__'
        read_only = ('shipment',)

    def validate_expiration_date(self, expiration_date):
        if expiration_date <= datetime.now(timezone.utc):
            raise exceptions.ValidationError('The expiration date should be greater than actual date')
        return expiration_date


class PermissionLinkCreateSerializer(PermissionLinkSerializer):
    emails = serializers.ListField(
        child=serializers.EmailField(),
        min_length=0,
        required=False
    )

    class Meta:
        model = PermissionLink
        fields = ('name', 'expiration_date', 'emails')
        read_only = ('shipment',)
