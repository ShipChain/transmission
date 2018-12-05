import decimal
import json
import re
import boto3

from botocore.client import Config
from drf_enum_field.fields import EnumField

from django.conf import settings


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


def get_s3_client():
    if settings.ENVIRONMENT in ('LOCAL', 'TEST'):
        s_3 = boto3.client(
            's3',
            endpoint_url=settings.S3_ENDPOINT,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            config=Config(signature_version='s3v4'),
            region_name='us-east-1'
        )

        s3_resource = boto3.resource(
            's3',
            endpoint_url=settings.S3_ENDPOINT,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            config=Config(signature_version='s3v4'),
            region_name='us-east-1'
        )
    else:
        s_3 = boto3.client(
            's3',
            endpoint_url=settings.S3_ENDPOINT,
            region_name='us-east-1'
        )

        s3_resource = None

    return s_3, s3_resource
