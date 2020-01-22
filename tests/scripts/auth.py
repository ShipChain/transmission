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

import datetime
import json
import pytz

import jwt

from conf.auth import SIMPLE_JWT
from conf.requests import REQUESTS_SESSION
from conf.base import PROFILES_ENABLED

LEEWAY = 10


class GetSessionJwt:
    def __init__(self, username, password, client_id, environment=None, profiles_host=None, schema='http'):
        self.username = username
        self.password = password
        self.client_id = client_id
        self.environment = environment
        self.host = profiles_host
        self.schema = schema

        self._current_jwt = None
        self._current_exp_date = None

    def __call__(self):
        current_date_time = datetime.datetime.now(tz=pytz.UTC)
        if not self._current_exp_date:
            self.set_new_token()
        elif current_date_time + datetime.timedelta(seconds=LEEWAY) < self._current_exp_date:
            # Token up to date no need to refresh
            pass
        else:
            # The token has expires or is about to
            self.set_new_token()
        return self._current_jwt

    def decode_jwt(self, encoded):
        return jwt.decode(
            encoded,
            key=SIMPLE_JWT['VERIFYING_KEY'],
            algorithm=SIMPLE_JWT['ALGORITHM'],
            audience=self.client_id
        )

    def refresh_jwt(self):
        if PROFILES_ENABLED:
            response = REQUESTS_SESSION.post(f'{self.schema}://{self.host}/openid/token/', data=json.dumps({
                'username': self.username,
                'password': self.password,
                'client_id': self.client_id,
                'grant_type': 'password',
                'scope': 'openid email'
            }))
            return response.json()['id_token']
        return None

    def set_new_token(self):
        self._current_jwt = self.refresh_jwt()
        if self._current_jwt is not None:
            decoded_jwt = self.decode_jwt(self._current_jwt)
            self._current_exp_date = datetime.datetime.fromtimestamp(decoded_jwt['exp']).astimezone(tz=pytz.UTC)
