import decimal
import json

import re
from django.contrib.auth import get_user_model
from enumfields.drf import EnumField


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


def snake_to_sentence(word):
    return ' '.join(x.capitalize() or '_' for x in word.split('_'))


def build_auth_headers_from_request(request):
    if not request.auth or not isinstance(request.auth, bytes):
        raise Exception("No auth in request")

    token = request.auth.decode('utf-8')
    return {'Authorization': f"JWT {token}"}


DN_REGEX = re.compile(r'(?:/?)(.+?)(?:=)([^/]+)')


def parse_dn(ssl_dn):
    return dict(DN_REGEX.findall(ssl_dn))


class DecimalEncoder(json.JSONEncoder):
    def default(self, o):  # pylint: disable=method-hidden
        if isinstance(o, decimal.Decimal):
            return float(o)
        return super(DecimalEncoder, self).default(o)


class UpperEnumField(EnumField):
    def to_representation(self, instance):
        return super(UpperEnumField, self).to_representation(instance).upper()


def get_username_field():
    try:
        username_field = get_user_model().USERNAME_FIELD
    except AttributeError:
        username_field = 'username'

    return username_field


def get_username(user):
    try:
        username = user.get_username()
    except AttributeError:
        username = user.username

    return username

