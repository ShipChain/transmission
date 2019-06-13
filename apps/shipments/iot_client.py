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

    def get_list_owner_devices(self, owner_id, active=None, in_bbox=None):
        LOG.debug(f'Getting devices for: {owner_id} from AWS IoT')
        log_metric('transmission.info', tags={'method': 'DeviceAWSIoTClient.get_list_owner_devices'})

        if in_bbox:
            in_bbox = ','.join([c.strip() for c in in_bbox.split(',')])

        loop = True
        next_token = None
        results = []
        while loop:
            params_dict = dict(ownerId=owner_id,
                               active=active if active is not None else '',
                               in_bbox=in_bbox if in_bbox else '',
                               maxResults=settings.IOT_DEVICES_PAGE_SIZE,
                               nextToken=next_token if next_token else '',)

            try:
                list_devices = self._get('devices', query_params=params_dict)
            except AWSIoTError as exc:
                if 'NotFoundError' in str(exc):
                    # AwsIoT couldn't list any device for the authenticated User/Org
                    break
                else:
                    raise AWSIoTError(str(exc))

            if 'error' in list_devices:
                LOG.error(f'IoT was not able to fulfill the following request, endpoint: "devices",'
                          f' params: {params_dict}. Error message: {list_devices["error"]}')
                raise AWSIoTError("Error in response from AWS IoT")

            new_devices = list_devices['data'].get('devices', None)
            if new_devices:
                results.extend(new_devices)

            next_token = list_devices['data'].get('nextToken', None)
            loop = True if next_token else False

        return results
