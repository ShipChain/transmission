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
from collections import OrderedDict

from django.conf import settings
from influxdb_metrics.loader import log_metric

from apps.iot_client import AWSIoTClient, AWSIoTError


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

        active = kwargs['active']
        in_bbox = kwargs['in_bbox']

        if in_bbox:
            in_bbox = ','.join([c.strip() for c in in_bbox.split(',')])

        if not next_token:
            results = []

        params_dict = OrderedDict(ownerId=owner_id,
                                  maxResults=settings.IOT_DEVICES_PAGE_SIZE,
                                  active=active if active is not None else '',
                                  in_bbox=in_bbox if in_bbox else '',
                                  nextToken=next_token if next_token else '',)

        list_devices = self._get('devices', query_params=params_dict)

        if 'error' in list_devices:
            raise AWSIoTError("Error in response from AWS IoT")

        new_devices = list_devices['data'].get('devices', None)
        if new_devices:
            results.extend(new_devices)

        next_token = list_devices['data'].get('nextToken', None)
        if next_token:
            return self.get_list_owner_devices(owner_id, next_token=next_token, results=results, active=active,
                                               in_bbox=in_bbox)

        return results
