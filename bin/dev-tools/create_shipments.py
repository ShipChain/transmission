#! /usr/bin/env python3

import argparse
import sys
import json
from json.decoder import JSONDecodeError
from datetime import datetime, timezone, timedelta
from urllib.parse import urlparse
from uuid import uuid4
from enum import Enum
import logging

from copy import deepcopy
from random import randint
import requests

# pylint:disable=invalid-name
logger = logging.getLogger('transmission')
console = logging.StreamHandler()


class CriticalError(Exception):
    def __init__(self, message):
        logger.critical(message)
        logger.removeHandler(console)
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
parser.add_argument("--count", "-t", help="Total amount of shipments to be created, defaults to 10", type=int,
                    default=10)
parser.add_argument("--startnumber", "-n", help="Number to start at for sequential attributes.", type=int,
                    default=0)
parser.add_argument("--partition", "-p", help="Maximum number of shipments to be created per wallet, defaults to 10.",
                    type=int, default=10)
parser.add_argument("--carrier", "-c", help="Set carrier wallet owner by passing in the username. Defaults to user1.",
                    choices=['user1@shipchain.io', 'user2@shipchain.io'], default='user1@shipchain.io')
parser.add_argument("--shipper", "-s", help="Set shipper wallet owner by passing in the username. Defaults to user1.",
                    choices=['user1@shipchain.io', 'user2@shipchain.io'], default='user1@shipchain.io')
parser.add_argument("--moderator", "-m",
                    help="Set moderator wallet owner by passing in the username. Defaults to user1.",
                    choices=['user1@shipchain.io', 'user2@shipchain.io'])
parser.add_argument("--loglevel", "-l", help="Set the logging level for the creator. Defaults to info.",
                    choices=list(LogLevels.__members__), default='info')
parser.add_argument("--device", "-d", help="Add devices to shipment creation, defaults to false",
                    action="store_true")
parser.add_argument("--attributes", "-a", action='append',
                    help="Attributes to be sent in shipment creation (defaults to required values). "
                         "Setting a key to ##RAND## sets the value as new uuid per creation, "
                         "and ##NUMB## is replaced with a number starting from the --startnumber "
                         "Format should be either {\"key\": \"value\"} or key = value. "
                         "EX: \'{\"forwarders_shipper_id\": \"##RAND##\", \"pro_number\": \"PRO_##NUMB##\"}\'")
parser.add_argument("--add_tracking", help="Adds tracking data to shipments (requires --device or -d)",
                    action='store_true')
parser.add_argument("--add_telemetry", help="Adds telemetry data to shipments (requires --device or -d)",
                    action='store_true')
parser.add_argument("--profiles_url", help="Sets the profiles url for the creator. Defaults to http://localhost:9000",
                    default='http://localhost:9000')
parser.add_argument("--transmission_url",
                    help="Sets the transmission url for the creator. Defaults to http://localhost:8000",
                    default='http://localhost:8000')
parser.add_argument("--reuse_wallets", help="Reuse wallets instead of creating new ones, defaults to True",
                    action="store_true",
                    default=True)
parser.add_argument("--reuse_storage_credentials",
                    help="Reuse storage credentials instead of creating a new one, defaults to True",
                    action="store_true",
                    default=True)


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
            'wallets': []
        }, 'user2@shipchain.io': {
            'username': 'user2@shipchain.io',
            'password': 'user2Password',
            'token': None,
            'token_exp': None,
            'wallets': []
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
    def __init__(self):
        self.attributes = {}
        self.errors = []
        self.shipments = []

    # pylint: disable=too-many-arguments, too-many-locals, attribute-defined-outside-init
    def set_shipment_fields(self, carrier='user1@shipchain.io', shipper='user1@shipchain.io', moderator=False,
                            startnumber=0, total=10, loglevel='warning', device=False, partition=10, attributes=None,
                            add_tracking=False, add_telemetry=False, profiles_url='http://localhost:9000',
                            transmission_url='http://localhost:8000', reuse_wallets=False,
                            reuse_storage_credentials=False):
        self.carrier = self.users[carrier]
        self.shipper = self.users[shipper]
        self.moderator = self.users[moderator] if moderator else None
        self.sequence_number = startnumber
        self.total = total
        console.setLevel(LogLevels[loglevel].value)
        logger.addHandler(console)
        logger.setLevel(LogLevels[loglevel].value)
        self.device = device
        self.partition = partition
        self.add_tracking = add_tracking
        self.add_telemetry = add_telemetry
        self.reuse_storage_credentials = reuse_storage_credentials
        self.reuse_wallets = reuse_wallets
        self.profiles_url = self._validate_url(profiles_url, 'profiles')
        self.transmission_url = self._validate_url(transmission_url, 'transmission')
        if attributes:
            self._validate_attributes(attributes)

    def _chunker(self, array):
        return (array[i:i + self.partition] for i in range(0, len(array), self.partition))

    def _validate_url(self, url, url_base):
        try:
            result = urlparse(url)
            if not result.scheme or not result.netloc:
                raise CriticalError(f'Invalid url supplied for {url_base}: {url}')
            return url
        except ValueError:
            raise CriticalError(f'Invalid url supplied for {url_base}: {url}')

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
            url_group = 'Profiles' if self.profiles_url in url else 'Transmission'
            raise CriticalError(
                f'Connection error raised when connecting to {url}. Ensure service {url_group} is running.')

        if not response.ok:
            if response.status_code == 503:
                logger.warning('Ensure Engine services are running.')
            self.errors += response.json()['errors']
            raise NonCriticalError(f'Invalid response returned from {url}')

        return response.json()

    def _retrieve_updated_attributes(self):
        logger.info('Updating attributes to remove/update random and sequential variables')
        updated_attributes = deepcopy(self.attributes)
        for key, value in updated_attributes.items():
            if "##RAND##" in value:
                updated_attributes[key] = value.replace("##RAND##", str(uuid4()))
            elif "##NUM##" in value:
                updated_attributes[key] = value.replace("##NUM##", self.sequence_number)
        if self.device:
            try:
                device_response = self._parse_request(
                    f"{self.profiles_url}/api/v1/device",
                    data={'device_type': "AXLE_GATEWAY"},
                    headers={'Authorization': 'JWT {}'.format(self.shipper['token'])})
            except NonCriticalError:
                raise CriticalError('Error generating device')
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

    def _reuse_wallets(self):
        logger.info('Reusing wallets for shipment')
        for wallet_owner in ('shipper', 'carrier', 'moderator'):
            wallet_owner_dict = getattr(self, wallet_owner)
            if not wallet_owner_dict:
                continue

            if not wallet_owner_dict['wallets']:
                logger.debug(f'Wallets not found for owner: {wallet_owner_dict["username"]}')
                try:
                    response = self._parse_request(
                        f"{self.profiles_url}/api/v1/wallet?page_size=9999", method='get',
                        headers={'Authorization': f'JWT {self.get_user_jwt(self.shipper)}'})
                except NonCriticalError:
                    raise CriticalError(f'Error retrieving wallets for user {wallet_owner_dict["username"]}.')

                logger.debug(f"Wallet count returned: {response['meta']['pagination']['count']}")
                if response['meta']['pagination']['count'] == 0 or response['meta']['pagination']['count'] \
                        < self.total // self.partition:
                    raise CriticalError(f'Not enough wallets for user {wallet_owner_dict["username"]}.')

                wallet_owner_dict['wallets'] = response['data']

            wallet = wallet_owner_dict['wallets'].pop()

            self.attributes[f'{wallet_owner}_wallet_id'] = wallet['id']

    def _generate_wallets(self):
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

    def _reuse_storage_credentials(self):
        logger.info('Reusing storage credentials.')
        try:
            response = self._parse_request(
                f"{self.profiles_url}/api/v1/storage_credentials",
                headers={'Authorization': f'JWT {self.get_user_jwt(self.shipper)}'}, method='get')
        except NonCriticalError:
            raise CriticalError('Error retrieving storage credentials')

        logger.debug(f'Storage credentials count returned: {response["meta"]["pagination"]["count"]}')
        if response['meta']['pagination']['count'] == 0:
            raise CriticalError(f'No storage credentials found associated with account {self.carrier["username"]}')

        self.attributes['storage_credentials_id'] = response['data'][0]['id']

    def _generate_storage_credentials(self):
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
            raise CriticalError('Error generating storage credentials.')

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
        logger.info('Creating shipment')
        try:
            response = self._parse_request(
                f"{self.transmission_url}/api/v1/shipments/",
                data=attributes,
                headers={'Authorization': f'JWT {self.get_user_jwt(self.shipper)}'})
        except NonCriticalError:
            logger.warning('Failed to create shipment.')
            return

        logger.debug(f'Created shipment: {response["data"]["id"]}')
        self.shipments.append(response['data']['id'])

        if self.add_tracking:
            self._add_tracking(attributes['device_id'])
        if self.add_telemetry:
            self._add_telemetry(attributes['device_id'])

    def create_bulk_shipments(self):
        try:
            (self._reuse_storage_credentials() if self.reuse_storage_credentials
             else self._generate_storage_credentials())
        except CriticalError:
            logger.critical(f'Response errors: {self.errors}')
            sys.exit(2)

        for i in range(self.total):
            if i % self.partition == 0:
                try:
                    self._reuse_wallets() if self.reuse_wallets else self._generate_wallets()
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
    args_dict = vars(args)
    shipment_creator = ShipmentCreator()
    try:
        shipment_creator.set_shipment_fields(**args_dict)
    except CriticalError:
        sys.exit(2)
    shipment_creator.create_bulk_shipments()
