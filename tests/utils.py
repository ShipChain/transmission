import re
from datetime import timedelta
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


def get_jwt(exp=None, sub='00000000-0000-0000-0000-000000000000', username='fake@shipchain.io', organization_id=None):
    payload = {'email': username, 'username': username, 'sub': sub,
               'aud': settings.SIMPLE_JWT['AUDIENCE']}

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
