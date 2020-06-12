#! /usr/bin/env python3

import argparse
import sys
import json
from json.decoder import JSONDecodeError
from datetime import datetime, timezone, timedelta
from uuid import uuid4
from enum import Enum
import logging

from copy import deepcopy
from random import randint
import requests

# pylint:disable=invalid-name
logger = logging.getLogger('transmission')


class CriticalError(Exception):
    def __init__(self, message):
        logger.critical(message)
        self.parameter = message

    def __str__(self):
        return repr(self.parameter)


class NonCriticalError(Exception):
    def __init__(self, message):
        logger.warning(message)
        self.parameter = message

    def __str__(self):
        return repr(self.parameter)


class LogLevels(Enum):
    critical = 'CRITICAL'
    error = 'ERROR'
    warning = 'WARNING'
    info = 'INFO'
    debug = 'DEBUG'

    def __str__(self):
        return self.value


parser = argparse.ArgumentParser()
parser.add_argument("--total", "-t", help="Total amount of shipments to be created, defaults to 10", type=int,
                    default=10)
parser.add_argument("--startnumber", "-n", help="Number to start at for sequential attributes", type=int,
                    default=0)
parser.add_argument("--partition", "-p", help="Number shipments to create per wallet, defaults to 10", type=int,
                    default=10)
parser.add_argument("--carrier", "-c", help="Set carrier wallet owner by passing in the username. Defaults to user1.",
                    choices=['user1@shipchain.io', 'user2@shipchain.io'], default='user1@shipchain.io')
parser.add_argument("--shipper", "-s", help="Set shipper wallet owner by passing in the username. Defaults to user1.",
                    choices=['user1@shipchain.io', 'user2@shipchain.io'], default='user1@shipchain.io')
parser.add_argument("--moderator", "-m",
                    help="Set moderator wallet owner by passing in the username. Defaults to user1.",
                    choices=['user1@shipchain.io', 'user2@shipchain.io'])
parser.add_argument("--loglevel", "-l", help="Set the logging level for the creator. Defaults to warning.",
                    choices=list(LogLevels.__members__), default='warning')
parser.add_argument("--device", "-d", help="Add devices to shipment creation, defaults to false",
                    action="store_true")
parser.add_argument("--attributes", "-a", action='append',
                    help="Attributes to be sent in shipment creation (defaults to required values). "
                         "Format should be either {\"key\": \"value\"} or key = value.")
parser.add_argument("--add_tracking", help="Adds tracking data to shipments (requires --device or -d)",
                    action='store_true')
parser.add_argument("--add_telemetry", help="Adds telemetry data to shipments (requires --device or -d)",
                    action='store_true')
parser.add_argument("--profiles_url", help="Sets the profiles url for the creator. Defaults to localhost:9000",
                    default='http://localhost:9000')
parser.add_argument("--transmission_url", help="Sets the transmission url for the creator. Defaults to localhost:8000",
                    default='http://localhost:8000')


# pylint:disable=too-many-instance-attributes
class ShipmentCreator:
    # Default variables for local use
    client_id = 892633
    users = {
        'user1@shipchain.io': {
            'username': 'user1@shipchain.io',
            'password': 'user1Password',
            'token': None,
            'token_exp': None,
        }, 'user2@shipchain.io': {
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

    # pylint: disable=too-many-arguments, too-many-locals
    def __init__(self, carrier='user1@shipchain.io', shipper='user1@shipchain.io', moderator=None, sequence_number=0,
                 total=10, loglevel='warning', device=False, partition=10, attributes=None, add_tracking=False,
                 add_telemetry=False, profiles_url='http://localhost:9000', transmission_url='http://localhost:8000'):
        self.attributes = {}
        self.errors = []
        self.shipments = []
        self.carrier = self.users[carrier]
        self.shipper = self.users[shipper]
        self.moderator = self.users[moderator] if moderator else None
        self.sequence_number = sequence_number
        self.total = total
        console = logging.StreamHandler()
        console.setLevel(LogLevels[loglevel].value)
        logger.addHandler(console)
        logger.setLevel(LogLevels[loglevel].value)
        self.device = device
        self.chunk_size = partition
        self.add_tracking = add_tracking
        self.add_telemetry = add_telemetry
        self.profiles_url = profiles_url
        self.transmission_url = transmission_url
        if attributes:
            self._validate_attributes(attributes)

    def handle_args(self, command_args):
        self.carrier = self.users[command_args.carrier]
        self.shipper = self.users[command_args.shipper]
        self.moderator = self.users[command_args.moderator] if command_args.moderator else None
        self.sequence_number = command_args.startnumber
        self.total = int(command_args.total)
        console = logging.StreamHandler()
        console.setLevel(LogLevels[command_args.loglevel].value)
        logger.addHandler(console)
        logger.setLevel(LogLevels[command_args.loglevel].value)
        self.device = command_args.device
        self.chunk_size = int(command_args.partition)
        self.add_tracking = command_args.add_tracking
        if self.add_tracking and not self.device:
            parser.error(f'--add_tracking requires --device or -d')
        self.add_telemetry = command_args.add_telemetry
        if self.add_telemetry and not self.device:
            parser.error(f'--add_telemetry requires --device or -d')
        self.profiles_url = command_args.profiles_url
        self.transmission_url = command_args.transmission_url
        if command_args.attributes:
            self._validate_attributes(command_args.attributes)

    def _chunker(self, array):
        return (array[i:i + self.chunk_size] for i in range(0, len(array), self.chunk_size))

    def _validate_attributes(self, attributes):
        logger.info(f'Validating attributes: {attributes}')
        for attribute in attributes:
            try:
                attribute = json.loads(attribute)
            except JSONDecodeError:
                logger.debug(f'Non json attribute recieved: {attribute}')
            if isinstance(attribute, dict):
                logger.debug(f'Dict attribute recieved: {attribute}')
                self.attributes.update(attribute)
            else:
                try:
                    key, value = attribute.split("=")
                except ValueError:
                    raise CriticalError(f'Invalid format for attribute: {attribute}, should be in format: key=value')
                self.attributes[key] = value

    def _parse_request(self, url, method='post', **kwargs):
        if method not in ['post', 'get', 'patch']:
            raise CriticalError(f'Invalid method: {method}')
        request_method = getattr(requests, method)
        try:
            response = request_method(url, **kwargs)
        except requests.exceptions.ConnectionError:
            raise CriticalError(f'Connection error raised when connecting to {url}')

        if not response.ok:
            self.errors += response.json()['errors']
            raise NonCriticalError(f'Invalid response returned from {url}')

        return response.json()

    def _retrieve_updated_attributes(self):
        logger.info('Updating attributes to remove/update random and sequential variables')
        updated_attributes = deepcopy(self.attributes)
        for key, value in updated_attributes.items():
            if value == "##RAND##":
                updated_attributes[key] = str(uuid4())
            elif value == "##NUM##":
                updated_attributes[key] = self.sequence_number
        if self.device:
            try:
                device_response = self._parse_request(
                    f"{self.profiles_url}/api/v1/device",
                    data={'device_type': "AXLE_GATEWAY"},
                    headers={'Authorization': 'JWT {}'.format(self.shipper['token'])})
            except NonCriticalError:
                raise CriticalError(f'Error generating device')
            updated_attributes['device_id'] = device_response['data']['id']
        self.sequence_number += 1
        return updated_attributes

    def get_user_jwt(self, user):
        if user['token_exp'] and user['token_exp'] < datetime.now(timezone.utc):
            logger.debug(f'User {user["username"]} has non-expired token')
            return user['token']

        response = self._parse_request(
            f"{self.profiles_url}/openid/token/",
            data={
                "username": user['username'],
                "password": user['password'],
                "client_id": self.client_id,
                "grant_type": "password",
                "scope": "openid email"
            })
        if not response:
            raise CriticalError(f'Error generating token for user {user["username"]}')

        user['token'] = response['id_token']
        # Give a buffer of 60 seconds to the token time check
        user['token_exp'] = datetime.now(timezone.utc) + timedelta(seconds=(response['expires_in'] - 60))
        return response['id_token']

    def _set_wallets(self):
        logger.info('Generating wallets for shipment')
        try:
            shipper_response = self._parse_request(
                f"{self.profiles_url}/api/v1/wallet/generate",
                headers={'Authorization': f'JWT {self.get_user_jwt(self.shipper)}'})
        except NonCriticalError:
            raise CriticalError(f'Error generating shipper wallet for user {self.shipper["username"]}.')
        try:
            carrier_response = self._parse_request(
                f"{self.profiles_url}/api/v1/wallet/generate",
                headers={'Authorization': f'JWT {self.get_user_jwt(self.carrier)}'})
        except NonCriticalError:
            raise CriticalError(f'Error generating carrier wallet for user {self.carrier["username"]}.')

        if self.moderator:
            try:
                moderator_response = self._parse_request(
                    f"{self.profiles_url}/api/v1/wallet/generate/",
                    headers={'Authorization': f'JWT {self.get_user_jwt(self.moderator)}'})
            except NonCriticalError:
                raise CriticalError(f'Error generating storage credentials for user {self.shipper["username"]}.')

            self.attributes['moderator_wallet_id'] = moderator_response['data']['id']
        self.attributes['shipper_wallet_id'] = shipper_response['data']['id']
        self.attributes['carrier_wallet_id'] = carrier_response['data']['id']

    def _set_storage_credentials(self):
        logger.info('Creating storage credentials.')
        try:
            response = self._parse_request(
                f"{self.profiles_url}/api/v1/storage_credentials", data={
                    'driver_type': 'local',
                    'base_path': '/shipments',
                    'options': "{}",
                    'title': f'Shipment creator SC: {str(uuid4())}'
                }, headers={'Authorization': f'JWT {self.get_user_jwt(self.shipper)}'})
        except NonCriticalError:
            raise CriticalError(f'Error generating storage .')

        if not response:
            raise CriticalError(f'Error generating storage credentials.')

        logger.debug(f'Created storage credentials: {response["data"]["id"]}')
        self.attributes['storage_credentials_id'] = response['data']['id']

    # pylint:disable=unused-variable
    def _add_telemetry(self, device_id):
        logger.info(f'Creating sensors for device: {device_id}')
        telemetry_data = []
        self.telemetry_data['device_id'] = device_id
        for i in range(3):
            attributes = {
                'name': f'Sensor: {str(uuid4())}',
                'hardware_id': f'Hardware_id: {str(uuid4())}',
                'units': 'c',
            }
            try:
                response = self._parse_request(
                    f'{self.profiles_url}/api/v1/device/{device_id}/sensor/',
                    data=attributes,
                    headers={'Authorization': f'JWT {self.get_user_jwt(self.shipper)}'}
                )

            except NonCriticalError:
                logger.warning(f'Failed to create sensor for device: {device_id}')
                continue

            logger.info(f'Created sensor {response["data"]["id"]} for device {device_id}')

            telemetry_copy = deepcopy(self.telemetry_data)
            telemetry_copy['hardware_id'] = attributes['hardware_id']
            telemetry_copy['sensor_id'] = response['data']['id']
            for j in range(3):
                telemetry_copy['value'] = randint(0, 100)
                telemetry_data.append({"payload": telemetry_copy})

        logger.info(f'Adding telemetry via device: {device_id}')
        telemetry_response = requests.post(
            f"{self.transmission_url}/api/v1/devices/{device_id}/telemetry",
            json=telemetry_data,
            headers={"Content-type": "application/json"}
        )
        if not telemetry_response.ok:
            logger.warning(f'Failed to add telemetry data for device: {device_id}')
        else:
            logger.info(f'Added telemetry data via device: {device_id}')

    def _add_tracking(self, device_id):
        logger.info(f'Adding tracking via device: {device_id}')
        self.tracking_data['device_id'] = device_id
        tracking_data_collection = [{"payload": self.tracking_data} for i in range(10)]
        tracking_response = requests.post(
            f"{self.transmission_url}/api/v1/devices/{device_id}/tracking",
            json=tracking_data_collection,
            headers={"Content-type": "application/json"}
        )
        if not tracking_response.ok:
            logger.warning(f'Failed to add tracking data for device: {device_id}')
        else:
            logger.info(f'Added tracking data via device: {device_id}')

    def _create_shipment(self):
        attributes = self._retrieve_updated_attributes()
        try:
            response = self._parse_request(
                f"{self.transmission_url}/api/v1/shipments/",
                data=attributes,
                headers={'Authorization': f'JWT {self.get_user_jwt(self.shipper)}'})
        except NonCriticalError:
            logger.warning(f'Failed to create shipment.')
            return

        self.shipments.append(response['data']['id'])

        if self.add_tracking:
            self._add_tracking(attributes['device_id'])
        if self.add_telemetry:
            self._add_telemetry(attributes['device_id'])

    def create_bulk_shipments(self):
        try:
            self._set_wallets()
            self._set_storage_credentials()
        except CriticalError:
            logger.critical(f'Response errors: {self.errors}')
            sys.exit(2)

        for i in range(self.total):
            if i % self.chunk_size != 0:
                try:
                    self._set_wallets()
                except CriticalError:
                    logger.critical(f'Response errors: {self.errors}')
                    break
            try:
                self._create_shipment()
            except NonCriticalError:
                logger.info(f'Errors when generating shipments: {self.errors}')

        logger.info(f'Shipments created: {len(self.shipments)}')
        logger.info(f'Shipment ids: {self.shipments}')


if __name__ == '__main__':
    args = parser.parse_args()
    shipment_creator = ShipmentCreator()
    shipment_creator.handle_args(args)
    shipment_creator.create_bulk_shipments()
