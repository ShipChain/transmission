import re
import random
from datetime import timedelta
from unittest.mock import Mock
from urllib import parse

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


def get_jwt(exp=None, sub='00000000-0000-0000-0000-000000000000', username='fake@shipchain.io', organization_id=None):
    payload = {'email': username, 'username': username, 'sub': sub,
               'aud': '892633'}

    if organization_id:
        payload['organization_id'] = organization_id

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


class Url:
    """
    A url object that can be compared with other url objects
    without regard to the vagaries of encoding, escaping, and ordering
    of parameters in query strings.
    """

    def __init__(self, url):
        parts = parse.urlparse(url)
        _query = frozenset(parse.parse_qsl(parts.query))
        _path = parse.unquote_plus(parts.path)
        parts = parts._replace(query=_query, path=_path)
        self.parts = parts

    def __eq__(self, other):
        return self.parts == other.parts

    def __hash__(self):
        return hash(self.parts)
