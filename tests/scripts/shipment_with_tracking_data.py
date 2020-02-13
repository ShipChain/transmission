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

import argparse
import json
import logging
import random
import datetime

import django
from rest_framework import status
import requests
from shipchain_common.utils import random_id

from .auth import GetSessionJwt

django.setup()

LOG = logging.getLogger('transmission')

parser = argparse.ArgumentParser()

parser.add_argument('-s', action='store',
                    dest='storage_id',
                    required=True,
                    help='UUID of the storage to use')

parser.add_argument('-w', action='store',
                    dest='shipper_wallet_id',
                    required=True,
                    help='UUID of the shipper wallet to use')

parser.add_argument('-c', action='store',
                    dest='client_id',
                    required=True,
                    help='Profiles client ID')

parser.add_argument('-u', action='store',
                    dest='username',
                    required=True,
                    help='Profiles username')

parser.add_argument('-p', action='store',
                    dest='password',
                    required=True,
                    help='Profiles password')

parser.add_argument('-n', action='store',
                    dest='shipment_number',
                    required=True,
                    type=int,
                    help='Number of shipment to create')

parser.add_argument('-p-host', action='store',
                    dest='profiles_host',
                    default='profiles-runserver:8000',
                    help='Profiles host name, required for environment different than local')

parser.add_argument('-env', action='store',
                    dest='env',
                    default='LOCAL',
                    help='Deployment environment')

parser.add_argument('-t-host', action='store',
                    dest='transmission_host',
                    default='transmission-runserver:8000',
                    help='Transmission host name, required for environment different than local')

parser.add_argument('-ntd', action='store',
                    dest='tracking_data_number',
                    type=int,
                    default=100,
                    help='Number of tracking data to add for each shipment')

parser.add_argument('-bbox', action='store',
                    dest='bbox',
                    default='-90.90,30.90,-78.80,36.80',
                    help='Number of tracking data to add for each shipment')


def get_object_id(object_dict):
    try:
        return object_dict['id']
    except KeyError:
        return object_dict['data']['id']


def create_shipment(shipment_url, shipment_fields, jwt):
    response = requests.post(shipment_url, data=shipment_fields,
                             headers={'Authorization': f'JWT {jwt}'}).json()['data']
    LOG.debug(f'Created shipment [{response["id"]}]')

    return response


def perform_shipment_action(action_url, jwt):
    from apps.shipments.serializers import ActionType

    response = requests.post(action_url, data={'action_type': ActionType.PICK_UP.name},
                             headers={'Authorization': f'JWT {jwt}'})
    if response.status_code == status.HTTP_200_OK:
        response = response.json()['data']
        LOG.debug(f'Shipment: [{response["id"]}] transited to [{response["attributes"]["state"]}]')


def create_random_device(device_url, jwt):
    response = requests.post(device_url,
                             data={'nickname': f'Random Device {random_id()}', 'device_type': 'AXLE_GATEWAY'},
                             headers={'Authorization': f'JWT {jwt}'})
    if response.ok:
        response = response.json()['data']
        LOG.debug(f'Created device: [{response["id"]}] with nickname: [{response["attributes"]["device_type"]}]')

    return response['id']


def get_tracking_data(device_pk, num_tracking_data, in_bbox):
    min_long, min_lat, max_long, max_lat = in_bbox

    point_data = {
        "payload": {
            "position": {
                "latitude": float,
                "longitude": float,
                "altitude": int,
                "source": "gps",
                "uncertainty": int,
                "speed": int
            },
            "version": "1.0.0",
            "device_id": device_pk,
            "timestamp": ''
        }
    }

    list_tracking_data = []
    for i in range(0, num_tracking_data):
        position = point_data['payload']['position']
        position['latitude'] = random.uniform(min_lat, max_lat)
        position['longitude'] = random.uniform(min_long, max_long)
        position['altitude'] = random.randint(1, 1000)
        position['uncertainty'] = random.randint(1, 99)
        position['speed'] = random.uniform(0, 999)

        point_data['payload']['timestamp'] = datetime.datetime.utcnow().isoformat()

        list_tracking_data.append(point_data)

    return list_tracking_data


def post_bulk_tracking_data(tracking_data_url, list_tracking_data, shipment_pk):
    response = requests.post(tracking_data_url,
                             data=json.dumps(list_tracking_data),
                             headers={'content-type': 'application/json'})

    if response.status_code == status.HTTP_204_NO_CONTENT:
        LOG.debug(f'Successfully added {len(tracking_data)} tracking data to shipment [{shipment_pk}]')


if __name__ == '__main__':
    arguments = parser.parse_args()

    schema = 'http' if arguments.env.lower() == 'local' else 'https'

    device_create_url = f'{schema}://{arguments.profiles_host}/api/v1/device'

    shipment_create_url = f'{schema}://{arguments.transmission_host}/api/v1/shipments'

    jwt_session = GetSessionJwt(username=arguments.username, password=arguments.password,
                                client_id=arguments.client_id, environment=arguments.env,
                                profiles_host=arguments.profiles_host, schema=schema)

    shipment_creation_data = {
        'storage_credentials_id': arguments.storage_id,
        'shipper_wallet_id': arguments.shipper_wallet_id,
        'carrier_wallet_id': arguments.shipper_wallet_id,
    }

    bbox = [float(item) for item in arguments.bbox.split(',')]

    for num in range(0, arguments.shipment_number):

        device_id = create_random_device(device_create_url, jwt_session())

        shipment_creation_data['device_id'] = device_id

        shipment_data = create_shipment(shipment_create_url, shipment_creation_data, jwt_session())
        shipment_id = get_object_id(shipment_data)

        shipment_action_url = f'{schema}://{arguments.transmission_host}/api/v1/shipments/' \
                              f'{shipment_id}/actions/'

        perform_shipment_action(shipment_action_url, jwt_session())

        add_tracking_data_url = f'{schema}://{arguments.transmission_host}/api/v1/devices/{device_id}/tracking'

        tracking_data = get_tracking_data(device_id, arguments.tracking_data_number, bbox)

        post_bulk_tracking_data(add_tracking_data_url, tracking_data, shipment_id)
