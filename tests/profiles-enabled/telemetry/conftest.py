#  Copyright 2020 ShipChain, Inc.
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.
import json
from datetime import datetime, timezone

import freezegun
import pytest
from copy import deepcopy
from jose import jws


@pytest.fixture
def unsigned_telemetry(current_datetime):
    return {
        'hardware_id': 'hardware_id',
        'sensor_id': 'sensor_id',
        'version': '1.2.4',
        'value': 3.14,
        'timestamp': current_datetime.isoformat().replace('+00:00', 'Z')
    }


@pytest.fixture
def current_datetime():
    return datetime.now(timezone.utc)


@pytest.fixture(autouse=True)
def frozen_time(current_datetime):
    with freezegun.freeze_time(current_datetime) as current_datetime:
        yield current_datetime


@pytest.fixture
def unsigned_telemetry_different_hardware(unsigned_telemetry):
    telemetry = deepcopy(unsigned_telemetry)
    telemetry['hardware_id'] = 'hardware_id_2'
    return telemetry


@pytest.fixture
def unsigned_telemetry_different_sensor(unsigned_telemetry):
    telemetry = deepcopy(unsigned_telemetry)
    telemetry['sensor_id'] = 'sensor_id_2'
    return telemetry


@pytest.fixture
def signed_telemetry(unsigned_telemetry, device):
    with open('tests/data/eckey.pem', 'r') as key_file:
        key_pem = key_file.read()

    return jws.sign(payload=json.dumps(unsigned_telemetry).encode(),
                    key=key_pem,
                    headers={'kid': device.certificate_id},
                    algorithm='ES256')


@pytest.fixture
def invalid_post_signed_telemetry(device):
    with open('tests/data/eckey.pem', 'r') as key_file:
        key_pem = key_file.read()

    return {
        'payload': jws.sign(payload=json.dumps({'timestamp': str(datetime.now())}).encode(),
                            key=key_pem,
                            headers={'kid': device.certificate_id},
                            algorithm='ES256')
    }


@pytest.fixture
def create_unsigned_telemetry_post(unsigned_telemetry):
    return {
        'payload': unsigned_telemetry
    }


@pytest.fixture
def create_signed_telemetry_post(signed_telemetry):
    return {
        'payload': signed_telemetry
    }


@pytest.fixture
def create_batch_signed_telemetry_post(signed_telemetry):
    return [{
        'payload': signed_telemetry
    }, {
        'payload': signed_telemetry
    }]


@pytest.fixture
def create_batch_unsigned_telemetry_post(unsigned_telemetry):
    return [{
        'payload': unsigned_telemetry
    }, {
        'payload': unsigned_telemetry
    }]
