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

import json
import logging

import boto3
from botocore.exceptions import ClientError, BotoCoreError
from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from dateutil.parser import parse

from jose import jws, JWSError
from rest_framework import exceptions, serializers as rest_serializers
from rest_framework_json_api import serializers

from apps.shipments.models import Device, TrackingData
from . import ShipmentSerializer

LOG = logging.getLogger('transmission')


class SignedDevicePayloadSerializer(serializers.Serializer):
    payload = serializers.RegexField(r'^[a-zA-Z0-9\-_]+?\.[a-zA-Z0-9\-_]+?\.([a-zA-Z0-9\-_]+)?$')

    def validate(self, attrs):  # noqa: MC0001
        iot = boto3.client('iot', region_name='us-east-1')
        payload = attrs['payload']
        shipment = self.context['shipment']
        try:
            header = jws.get_unverified_header(payload)
        except JWSError as exc:
            raise exceptions.ValidationError(f"Invalid JWS: {exc}")

        certificate_id_from_payload = header['kid']

        # Ensure that the device is allowed to update the Shipment tracking data
        if not shipment.device:
            raise exceptions.PermissionDenied(f"No device for shipment {shipment.id}")

        elif certificate_id_from_payload != shipment.device.certificate_id:
            try:
                iot.describe_certificate(certificateId=certificate_id_from_payload)
            except BotoCoreError as exc:
                LOG.warning(f'Found dubious certificate: {certificate_id_from_payload}, on shipment: {shipment.id}')
                raise exceptions.PermissionDenied(f"Certificate: {certificate_id_from_payload}, is invalid: {exc}")

            device = shipment.device
            device.certificate_id = Device.get_valid_certificate(device.id)
            device.save()

            if certificate_id_from_payload != device.certificate_id:
                raise exceptions.PermissionDenied(f"Certificate {certificate_id_from_payload} is "
                                                  f"not associated with shipment {shipment.id}")

        try:
            # Look up JWK for device from AWS IoT
            cert = iot.describe_certificate(certificateId=certificate_id_from_payload)

            if cert['certificateDescription']['status'] == 'ACTIVE':
                # Get public key PEM from x509 cert
                certificate = cert['certificateDescription']['certificatePem'].encode()
                public_key = x509.load_pem_x509_certificate(certificate, default_backend()).public_key().public_bytes(
                    encoding=Encoding.PEM, format=PublicFormat.SubjectPublicKeyInfo).decode()

                # Validate authenticity and integrity of message signature
                attrs['payload'] = json.loads(jws.verify(payload, public_key, header['alg']).decode("utf-8"))
            else:
                raise exceptions.PermissionDenied(f"Certificate {certificate_id_from_payload} is "
                                                  f"not ACTIVE in IoT for shipment {shipment.id}")
        except ClientError as exc:
            raise exceptions.APIException(f'boto3 error when validating tracking update: {exc}')
        except JWSError as exc:
            raise exceptions.PermissionDenied(f'Error validating tracking data JWS: {exc}')

        return attrs


class UnvalidatedDevicePayloadSerializer(serializers.Serializer):
    payload = serializers.JSONField()

    def validate(self, attrs):
        shipment = self.context['shipment']

        # Ensure that the device is allowed to update the Shipment tracking data
        if not shipment.device:
            raise exceptions.PermissionDenied(f"No device for shipment {shipment.id}")

        return attrs


class BaseDataToDbSerializer(rest_serializers.ModelSerializer):
    shipment = ShipmentSerializer(read_only=True)

    def __init__(self, *args, **kwargs):
        # Ensure that the timestamps is valid
        try:
            kwargs['data']['timestamp'] = parse(kwargs['data']['timestamp'])
        except Exception as exception:
            raise exceptions.ValidationError(detail=f"Unable to parse tracking data timestamp in to datetime object: \
                                                    {exception}")

        super().__init__(*args, **kwargs)


class TrackingDataToDbSerializer(BaseDataToDbSerializer):
    """
    Serializer for tracking data to be cached in db
    """
    def __init__(self, *args, **kwargs):
        if 'position' not in kwargs['data']:
            raise exceptions.ValidationError(detail='Unable to find `position` field in body.')
        kwargs['data'].update(kwargs['data'].pop('position'))

        super().__init__(*args, **kwargs)

    class Meta:
        model = TrackingData
        exclude = ('point', 'time', 'device')

    def create(self, validated_data):
        return TrackingData.objects.create(**validated_data, **self.context)
