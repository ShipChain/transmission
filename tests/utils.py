import re
import random
import pytz
from datetime import datetime, timedelta
from unittest.mock import Mock

import jwt
from django.conf import settings
from django.test.client import encode_multipart
from requests.models import Response
from rest_framework_simplejwt.utils import aware_utcnow, datetime_to_epoch


def replace_variables_in_string(string, parameters):
    matches = re.findall("<<(\w+?)>>", string)
    for match in matches:
        string = string.replace(f"<<{match}>>", parameters[match])
    return string


def create_form_content(data):
    boundary_string = 'BoUnDaRyStRiNg'
    content = encode_multipart(boundary_string, data)
    content_type = 'multipart/form-data; boundary=' + boundary_string
    return content, content_type


def mocked_rpc_response(json, code=200):
    response = Mock(spec=Response)
    response.status_code = code
    response.json.return_value = json
    return response


def get_jwt(exp=None, sub='00000000-0000-0000-0000-000000000000', username='fake@shipchain.io',
            organization_id=None, monthly_rate_limit=None, background_data_hash_interval=None,
            manual_update_hash_interval=None):
    payload = {'email': username, 'username': username, 'sub': sub,
               'aud': '892633'}

    if organization_id:
        payload['organization_id'] = organization_id

    if monthly_rate_limit:
        payload['monthly_rate_limit'] = monthly_rate_limit

    if background_data_hash_interval:
        payload['background_data_hash_interval'] = background_data_hash_interval

    if background_data_hash_interval:
        payload['manual_update_hash_interval'] = manual_update_hash_interval

    now = aware_utcnow()
    if exp:
        payload['exp'] = exp
    else:
        payload['exp'] = datetime_to_epoch(now + timedelta(minutes=5))

    payload['iat'] = datetime_to_epoch(now)

    return jwt.encode(payload=payload, key=settings.SIMPLE_JWT['PRIVATE_KEY'], algorithm='RS256',
                      headers={'kid': '230498151c214b788dd97f22b85410a5'}).decode('utf-8')


def random_timestamp():
    def is_one(a, b):
        value = str(random.randint(a, b))
        if len(value) == 1:
            return '0' + value
        return value

    return f'201{random.randint(6,9)}-{is_one(1,9)}-{is_one(1,30)}T{is_one(0,24)}:{is_one(0,59)}:{is_one(0,59)}.' \
        f'{random.randint(1000,9999)}'


def random_location():
    """
    :return: Randomly generated location geo point.
    """
    return {
        "geometry": {
            "coordinates": [random.uniform(-180, 180), random.uniform(-90, 90)],
            "type": "Point"
        },
        "properties": {
            "source": "Gps",
            "time": random_timestamp(),
            "uncertainty": random.randint(0, 99)
        },
        "type": "Feature"
    }


def datetimeAlmostEqual(dt1, dt2=None):
    if not dt2:
        dt2 = datetime.now().replace(tzinfo=pytz.UTC)
    return dt1.replace(second=0, microsecond=0) == dt2.replace(second=0, microsecond=0)


class GeoCoderResponse:
    def __init__(self, status, point=None):
        self.ok = status
        self.xy = point
