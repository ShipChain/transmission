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

from influxdb_metrics.loader import log_metric
from shipchain_common.aws import URLShortenerClient
from shipchain_common.exceptions import AWSIoTError, URLShortenerError
from shipchain_common.iot import AWSIoTClient

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


class URLShortener(URLShortenerClient):
    def get_shortened_link(self, params):
        url_response = self._post(payload=params)

        if 'short_id' not in url_response:
            raise URLShortenerError("Error generating short url for Permission Link")

        return f'{self.url}/{url_response["short_id"]}'
