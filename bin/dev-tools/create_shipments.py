#! /usr/bin/env python3

import argparse
import sys
import json
from json.decoder import JSONDecodeError
from datetime import datetime, timezone, timedelta
from uuid import uuid4

from copy import deepcopy
from random import randint
import requests

# pylint:disable=invalid-name
parser = argparse.ArgumentParser()
parser.add_argument("--total", "-t", help="Total amount of shipments to be created, defaults to 10", type=int)
parser.add_argument("--startnumber", "-n", help="Number to start at for sequential attributes", type=int)
parser.add_argument("--partition", "-p", help="Number shipments to create per wallet, defaults to 10", type=int)
parser.add_argument("--carrier", "-c", help="Set carrier wallet owner (defaults to user 1)")
parser.add_argument("--shipper", "-s", help="Set shipper wallet owner (defaults to user 1)")
parser.add_argument("--moderator", "-m", help="Set moderator wallet owner (defaults to None)")
parser.add_argument("--verbose", "-v", help="More descriptive when running functions.", action="store_true")
parser.add_argument("--device", "-d", help="Add devices to shipment creation, defaults to false",
                    action="store_true")
parser.add_argument("--attributes", "-a", action='append',
                    help="Attributes to be sent in shipment creation (defaults to required values)")
parser.add_argument("--add_tracking", help="Adds tracking data to shipments (requires --device or -d)",
                    action='store_true')
parser.add_argument("--add_telemetry", help="Adds telemetry data to shipments (requires --device or -d)",
                    action='store_true')

# Keep all but the first command-line arguments
argument_list = sys.argv[1:]


# pylint:disable=too-many-instance-attributes
class CreateShipments:
    # Default variables for local use
    profiles_url = 'http://localhost:9000'
    transmission_url = 'http://localhost:8000'
    client_id = 892633
    users = {
        'user_1': {
            'username': 'user1@shipchain.io',
            'password': 'user1Password',
            'token': None,
            'token_exp': None,
        }, 'user_2': {
            'username': 'user2@shipchain.io',
            'password': 'user2Password',
            'token': None,
            'token_exp': None,
        }
    }
    tracking_data = {
        "position": {
            "latitude": -81.048253,
            "longitude": 34.628643,
            "altitude": 924,
            "source": "gps",
            "uncertainty": 95,
            "speed": 34
        },
        "version": "1.2.4",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    telemetry_data = {
        "version": "1.2.4",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    # Values that can be set via command line
    attributes = {}

    # Values that cannot be set via command line but dynamic within function
    errors = []
    shipments = []

    def __init__(self):
        self.active_users = {'user_1'}
        args = parser.parse_args()
        self.carrier = self._validate_user(args.carrier) if args.carrier else self.users['user_1']
        self.shipper = self._validate_user(args.shipper) if args.shipper else self.users['user_1']
        self.moderator = self._validate_user(args.moderator) if args.moderator else None
        self.sequence_number = args.startnumber if args.startnumber else 0
        self.total = int(args.total) if args.total else 10
        self.verbose = args.verbose
        self.device = args.device
        self.chunk_size = int(args.partition) if args.partition else 10
        self.add_tracking = args.add_tracking
        if self.add_tracking and not self.device:
            parser.error(f'--add_tracking requires --device or -d')
        self.add_telemetry = args.add_telemetry
        if self.add_telemetry and not self.device:
            parser.error(f'--add_telemetry requires --device or -d')
        if args.attributes:
            self._validate_attributes(args.attributes)
        if self.users['user_1'] not in (self.moderator, self.carrier, self.shipper):
            self.active_users.remove('user_1')

    def _chunker(self, array):
        return (array[i:i + self.chunk_size] for i in range(0, len(array), self.chunk_size))

    def _validate_user(self, user):
        if user not in self.users:
            self._process_failure(f'Invalid user: {user}')
        if user not in self.active_users:
            self.active_users.add(user)
        return self.users[user]

    def _validate_attributes(self, attributes):
        if self.verbose:
            print(f'Validating attributes: {attributes}')
        for attribute in attributes:
            try:
                attribute = json.loads(attribute)
            except JSONDecodeError:
                if self.verbose:
                    print(f'Non json attribute recieved: {attribute}')
            if isinstance(attribute, dict):
                self.attributes.update(attribute)
            else:
                try:
                    key, value = attribute.split("=")
                except ValueError:
                    self._process_failure(f'Invalid format for attribute: {attribute}, should be in format: key=value')
                self.attributes[key] = value

    def _process_failure(self, error_message):
        print(f'Shipment Creator failed: {error_message}')
        print(f'Response errors: {self.errors}')
        sys.exit(2)

    def _parse_request(self, url, method='post', **kwargs):
        if method not in ['post', 'get', 'patch']:
            self._process_failure(f'Invalid method: {method}')
        request_method = getattr(requests, method)
        try:
            response = request_method(url, **kwargs)
        except requests.exceptions.ConnectionError:
            if self.verbose:
                print(f'Connection error raised when connecting to {url}')
            self._process_failure(f'Error connecting to url: {url}')

        if not response.ok:
            if self.verbose:
                print(f'Invalid response returned from {url}')
            self.errors += response.json()['errors']
            return None
        return response.json()

    def _retrieve_updated_attributes(self):
        if self.verbose:
            print(f'Updating attributes to remove update random and sequential variables')
        updated_attributes = deepcopy(self.attributes)
        for key, value in updated_attributes.items():
            if value == "##RAND##":
                updated_attributes[key] = str(uuid4())
            elif value == "##NUM##":
                updated_attributes[key] = self.sequence_number
        if self.device:
            device_response = self._parse_request(
                f"{self.profiles_url}/api/v1/device",
                data={'device_type': "AXLE_GATEWAY"},
                headers={'Authorization': 'JWT {}'.format(self.shipper['token'])})
            if not device_response:
                self._process_failure(f'Error generating device')
            updated_attributes['device_id'] = device_response['data']['id']
        self.sequence_number += 1
        return updated_attributes

    def _set_user_tokens(self):
        for user in self.active_users:
            if self.users[user]['token_exp'] and (self.users[user]['token_exp'] < datetime.now(timezone.utc)):
                continue
            response = self.get_user_jwt(self.users[user]['username'], self.users[user]['password'])
            if not response:
                self._process_failure(f'Error generating tokens')

            self.users[user]['token'] = response['id_token']
            self.users[user]['token_exp'] = datetime.now(timezone.utc) + timedelta(seconds=response['expires_in'])

    def get_user_jwt(self, username, password):
        response = self._parse_request(
            f"{self.profiles_url}/openid/token/",
            data={
                "username": username,
                "password": password,
                "client_id": self.client_id,
                "grant_type": "password",
                "scope": "openid email"
            })
        if not response:
            print(self.errors)
            sys.exit(2)

        return response

    def _set_wallets(self):
        if self.verbose:
            print('Generating wallets for shipment')
        shipper_response = self._parse_request(
            f"{self.profiles_url}/api/v1/wallet/generate",
            headers={'Authorization': 'JWT {}'.format(self.shipper['token'])})
        carrier_response = self._parse_request(
            f"{self.profiles_url}/api/v1/wallet/generate",
            headers={'Authorization': 'JWT {}'.format(self.carrier['token'])})
        if not shipper_response or not carrier_response:
            if self.verbose:
                print(f'Error generating {"shipper" if not shipper_response else "carrier"} wallet.')

            self._process_failure(f'Error generating wallets')

        if self.moderator:
            moderator_response = self._parse_request(
                f"{self.profiles_url}/api/v1/wallet/generate/",
                headers={'Authorization': 'JWT {}'.format(self.moderator['token'])})
            if not moderator_response:
                if self.verbose:
                    print(f'Error generating moderator wallet.')
                self._process_failure(f'Error generating moderator wallets')

            self.attributes['moderator_wallet_id'] = moderator_response['data']['id']
        self.attributes['shipper_wallet_id'] = shipper_response['data']['id']
        self.attributes['carrier_wallet_id'] = carrier_response['data']['id']

    def _set_storage_credentials(self):
        if self.verbose:
            print(f'Creating storage credentials.')

        response = self._parse_request(
            f"{self.profiles_url}/api/v1/storage_credentials", data={
                'driver_type': 'local',
                'base_path': '/shipments',
                'options': "{}",
                'title': f'Shipment creator SC: {str(uuid4())}'
            }, headers={'Authorization': 'JWT {}'.format(self.shipper['token'])})

        if not response:
            self._process_failure(f'Error generating storage credentials')

        if self.verbose:
            print(f'Created storage credentials: {response["data"]["id"]}')
        self.attributes['storage_credentials_id'] = response['data']['id']

    # pylint:disable=unused-variable
    def _add_telemetry(self, device_id):
        if self.verbose:
            print(f'Creating sensors for device: {device_id}')
        telemetry_data = []
        self.telemetry_data['device_id'] = device_id
        for i in range(3):
            attributes = {
                'name': f'Sensor: {str(uuid4())}',
                'hardware_id': f'Hardware_id: {str(uuid4())}',
                'units': 'c',
            }
            response = self._parse_request(
                f'{self.profiles_url}/api/v1/device/{device_id}/sensor/',
                data=attributes,
                headers={'Authorization': 'JWT {}'.format(self.shipper['token'])}
            )
            if not response:
                print(f'{"Failed to create" if not response.ok else "created"} sensor for device: {device_id}')
                continue

            telemetry_copy = deepcopy(self.telemetry_data)
            telemetry_copy['hardware_id'] = attributes['hardware_id']
            telemetry_copy['sensor_id'] = response['data']['id']
            for j in range(3):
                telemetry_copy['value'] = randint(0, 100)
                telemetry_data.append({"payload": telemetry_copy})
        if self.verbose:
            print(f'Adding telemetry via device: {device_id}')
        telemetry_response = requests.post(
            f"{self.transmission_url}/api/v1/devices/{device_id}/telemetry",
            json=telemetry_data,
            headers={"Content-type": "application/json"}
        )
        if self.verbose:
            print(f'{"Failed to add" if not telemetry_response.ok else "Added"} tracking via device: {device_id}')

    def _add_tracking(self, device_id):
        if self.verbose:
            print(f'Adding tracking via device: {device_id}')
        self.tracking_data['device_id'] = device_id
        # py
        tracking_data_collection = [{"payload": self.tracking_data} for i in range(10)]
        tracking_response = requests.post(
            f"{self.transmission_url}/api/v1/devices/{device_id}/tracking",
            json=tracking_data_collection,
            headers={"Content-type": "application/json"}
        )
        if self.verbose:
            print(f'{"Failed to add" if not tracking_response.ok else "Added"} '
                  f'tracking via device: {device_id}')

    def _create_shipment(self):
        attributes = self._retrieve_updated_attributes()
        response = self._parse_request(
            f"{self.transmission_url}/api/v1/shipments/",
            data=attributes,
            headers={'Authorization': 'JWT {}'.format(self.shipper['token'])})
        if not response:
            return
        self.shipments.append(response['data']['id'])

        if self.add_tracking:
            self._add_tracking(attributes['device_id'])
        if self.add_telemetry:
            self._add_telemetry(attributes['device_id'])

    def create_bulk_shipments(self):
        if self.verbose:
            print('Generating user tokens')
        self._set_user_tokens()
        self._set_wallets()
        self._set_storage_credentials()
        for i in range(self.total):
            if i % self.chunk_size != 0:
                self._set_user_tokens()
                self._set_wallets()
            self._create_shipment()

        print(f'Shipments created: {len(self.shipments)}')
        if self.verbose:
            print(f'Shipment ids: {self.shipments}')
        print(f'Response Errors: {self.errors}')


shipment_creator = CreateShipments()
shipment_creator.create_bulk_shipments()
