import re
from unittest.mock import Mock

from django.test.client import encode_multipart
from requests.models import Response
from rest_framework.test import APIClient


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


class APIClient(APIClient):
    def force_authenticate(self, user=None, token=None):
        """
        Forcibly authenticates outgoing requests with the given
        user and/or token.
        """
        self.handler._force_user = user
        self.handler._force_token = token
        if user is None:
            self.logout()  # Also clear any possible session info if required
