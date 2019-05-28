"""
Copyright 2018 ShipChain, Inc.

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

from django.conf import settings
from rest_framework.exceptions import ParseError
from influxdb_metrics.loader import log_metric

from apps.iot_client import AWSIoTClient, AWSIoTError
from apps.utils import is_uuid


LOG = logging.getLogger('transmission')


class DeviceAWSIoTClient(AWSIoTClient):
    def update_shadow(self, device_id, shadow):
        LOG.debug(f'Updating Device Shadow in AWS IoT')
        log_metric('transmission.info', tags={'method': 'device.aws_iot.update_shadow'})

        payload = {"data": shadow}

        iot_shadow = self._put(f'device/{device_id}/config', payload)

        if 'data' not in iot_shadow:
            raise AWSIoTError("Error in response from AWS IoT")

        return iot_shadow['data']

    def get_list_owner_devices(self, owner_id, next_token=None, results=None, **kwargs):
        LOG.debug(f'Getting devices for: {owner_id} from AWS IoT')
        log_metric('transmission.info', tags={'method': 'DeviceAWSIoTClient.get_list_owner_devices'})

        active = kwargs.get('active', None)
        in_bbox = kwargs.get('in_bbox', None)

        if in_bbox:
            in_bbox = ','.join([c.strip() for c in in_bbox.split(',')])
            in_bbox_is_valid, message = self.validate_in_bbox(in_bbox)
            if not in_bbox_is_valid:
                raise ParseError(message)

        if not next_token:
            results = []

        list_devices = self._get(f'devices?ownerId={owner_id}&maxResults={settings.IOT_DEVICES_MAX_RESULTS}'
                                 f'&nextToken={next_token if next_token else ""}'
                                 f'&in_bbox={in_bbox if in_bbox else ""}')

        if 'error' in list_devices:
            raise AWSIoTError("Error in response from AWS IoT")

        new_devices = list_devices['data'].get('devices', None)
        if new_devices:
            results.extend(new_devices)

        next_token = list_devices['data'].get('nextToken', None)
        if next_token:
            return self.get_list_owner_devices(owner_id, next_token=next_token, results=results, active=active,
                                               in_box=in_bbox)
        if active:
            device_status = active.lower()
            if device_status == 'true':
                results = self.filter_list_devices(results)[0]
            elif device_status == 'false':
                results = self.filter_list_devices(results)[1]
            else:
                raise ParseError(f'Invalid query parameter: {device_status}')

        return results

    def filter_list_devices(self, list_device):
        """
        Returns the list of current active / inactive devices
        """
        active_devices = []
        for device in list_device:
            reported = device['shadowData']['reported']
            if isinstance(reported, dict) and is_uuid(reported.get('shipmentId', None)):
                active_devices.append(list_device.pop(list_device.index(device)))

        return active_devices, list_device

    def validate_in_bbox(self, in_bbox):
        """
        returns a tuple (bool, message) where bool indicates whether the passed in in_box is valid or not
        and message is the related error message if any.

        :param in_bbox: string tuple like, which defines the viewport rectangle boundaries
                        format: min Lon, min Lat, max Lon, max Lat
        """
        long_range = (-180, 180)
        lat_range = (-90, 90)
        box_ranges = (long_range, lat_range, long_range, lat_range)

        list_box = in_bbox.split(',')
        if len(list_box) < 4:
            return False, f'in_box parameter takes 4 position parameters but {len(list_box)}, were passed in.'

        for box_value, rang, index in zip(list_box, box_ranges, range(1, 5)):
            try:
                box_value = float(box_value)
            except ValueError:
                return False, f'in_box coordinate: {box_value}, should be type number'

            if not rang[0] <= box_value <= rang[1]:
                return False, f'in_box coordinate in position: {index}, value: {box_value}, should be in range: {rang}'

        return True, 'ok'
