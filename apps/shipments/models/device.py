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

import boto3
from botocore.exceptions import ClientError
from django.conf import settings
from django.db import models
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.status import HTTP_200_OK
from rest_framework_json_api import serializers

LOG = logging.getLogger('transmission')


class Device(models.Model):
    id = models.CharField(primary_key=True, null=False, max_length=36)
    certificate_id = models.CharField(unique=True, null=True, blank=False, max_length=255)

    @staticmethod
    def get_or_create_with_permission(jwt, device_id):
        certificate_id = None
        if settings.PROFILES_ENABLED:
            # Make a request to Profiles /api/v1/devices/{device_id} with the user's JWT
            response = settings.REQUESTS_SESSION.get(f'{settings.PROFILES_URL}/api/v1/device/{device_id}/',
                                                     headers={'Authorization': f'JWT {jwt}'})
            if response.status_code != HTTP_200_OK:
                raise ValidationError("User does not have access to this device in ShipChain Profiles")

        device, created = Device.objects.get_or_create(id=device_id, defaults={'certificate_id': certificate_id})

        if settings.ENVIRONMENT not in ('LOCAL', 'INT'):
            # We update the related device with this certificate in case it exists
            if not created:
                device.certificate_id = Device.get_valid_certificate(device_id)
                device.save()

        return device

    @staticmethod
    def get_valid_certificate(device_id):
        certificate_id = None
        iot = boto3.client('iot', region_name='us-east-1')

        try:
            response = iot.list_thing_principals(thingName=device_id)
            if not len(response['principals']) > 0:  # pylint:disable=len-as-condition
                raise PermissionDenied(f"No certificates found for device {device_id} in AWS IoT")
            for arn in response['principals']:
                # arn == arn:aws:iot:us-east-1:489745816517:cert/{certificate_id}
                certificate_id = arn.rsplit('/', 1)[1]
                try:
                    certificate = iot.describe_certificate(certificateId=certificate_id)
                    if certificate['certificateDescription']['status'] != 'ACTIVE':
                        certificate_id = None
                    else:
                        break
                except ClientError as exc:
                    LOG.warning(f"Encountered error: {exc}, while parsing certificate: {certificate_id}")

        except iot.exceptions.ResourceNotFoundException:
            raise PermissionDenied(f"Specified device {device_id} does not exist in AWS IoT")
        except Exception as exception:
            raise PermissionDenied(f"Unexpected error: {exception}, occurred while trying to retrieve device: "
                                   f"{device_id}, from AWS IoT")

        return certificate_id

    def prepare_for_reassignment(self):
        if hasattr(self, 'shipment'):
            if not self.shipment.can_disassociate_device():
                raise serializers.ValidationError('Device is already assigned to a Shipment in progress')
            else:
                from apps.shipments.models import Shipment
                shipment = Shipment.objects.get(pk=self.shipment.id)
                shipment.device_id = None
                shipment.save()

        if hasattr(self, 'route'):
            from apps.routes.models import Route
            if not self.route.can_disassociate_device():
                raise serializers.ValidationError('Device is already assigned to a Route in progress')
            route = Route.objects.get(pk=self.route.id)
            route.device_id = None
            route.save()
