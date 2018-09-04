import json
import decimal
from collections import namedtuple
from rest_framework import exceptions
from rest_framework_jwt.settings import api_settings
from rest_framework_jwt.authentication import JSONWebTokenAuthentication
from drf_enum_field.fields import EnumField


def random_id():
    """
    Cast the UUID to a string
    """
    from uuid import uuid4
    return str(uuid4())


def assertDeepAlmostEqual(test_case, expected, actual, *args, **kwargs):  # nopep8 pylint: disable=invalid-name
    """
    Assert that two complex structures have almost equal contents.

    Compares lists, dicts and tuples recursively. Checks numeric values
    using test_case's :py:meth:`unittest.TestCase.assertAlmostEqual` and
    checks all other values with :py:meth:`unittest.TestCase.assertEqual`.
    Accepts additional positional and keyword arguments and pass those
    intact to assertAlmostEqual() (that's how you specify comparison
    precision).

    :param test_case: TestCase object on which we can call all of the basic
    'assert' methods.
    :type test_case: :py:class:`unittest.TestCase` object
    """
    is_root = '__trace' not in kwargs
    trace = kwargs.pop('__trace', 'ROOT')
    try:
        if isinstance(expected, (int, float, int, complex)):
            test_case.assertAlmostEqual(expected, actual, *args, **kwargs)
        elif isinstance(expected, dict):
            test_case.assertEqual(set(expected), set(actual))
            for key in expected:
                assertDeepAlmostEqual(test_case, expected[key], actual[key],
                                      __trace=repr(key), *args, **kwargs)
        else:
            test_case.assertEqual(expected, actual)
    except AssertionError as exc:
        exc.__dict__.setdefault('traces', []).append(trace)
        if is_root:
            trace = ' -> '.join(reversed(exc.traces))
            exc = AssertionError("%s\nTRACE: %s" % (str(exc), trace))
        raise exc


class EnumToNameField(EnumField):
    def to_internal_value(self, data):
        return super(EnumToNameField, self).to_internal_value(data).name


class AuthenticatedUser:
    def __init__(self, payload):
        self.id = payload.get('user_id')  # pylint:disable=invalid-name
        self.username = payload.get('username')
        self.email = payload.get('email')

    def is_authenticated(self):
        return True

    def is_staff(self):
        return False

    def is_superuser(self):
        return False


class PassiveJSONWebTokenAuthentication(JSONWebTokenAuthentication):

    def authenticate_credentials(self, payload):
        if 'sub' not in payload:
            raise exceptions.AuthenticationFailed('Invalid payload.')

        payload['pk'] = payload['sub']
        payload = namedtuple("User", payload.keys())(*payload.values())
        payload = api_settings.JWT_PAYLOAD_HANDLER(payload)

        user = AuthenticatedUser(payload)

        return user


def snake_to_sentence(word):
    return ' '.join(x.capitalize() or '_' for x in word.split('_'))


def build_auth_headers_from_request(request):
    if not request.auth or not isinstance(request.auth, bytes):
        raise Exception("No auth in request")

    token = request.auth.decode('utf-8')
    return {'Authorization': f"JWT {token}"}


class DecimalEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, decimal.Decimal):
            return float(o)
        return super(DecimalEncoder, self).default(o)
