import decimal
import json

import re
from django.db import models
from django.conf import settings
from django.core.mail import EmailMessage
from django.template.loader import render_to_string
from django.utils import six
from django.core.serializers import serialize

from enumfields.drf import EnumField
from simple_history.models import HistoricalRecords, ModelChange, ModelDelta


RELATED_TO_LOCATION = ('shipment_to', 'shipment_from', 'shipment_dest', 'shipment_bill', )


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


class EnumIntegerFieldLabel(EnumField):
    def to_representation(self, instance):
        return str(instance)


class AliasField(models.Field):
    def contribute_to_class(self, cls, name, private_only=False):
        """
            virtual_only is deprecated in favor of private_only
        """
        super(AliasField, self).contribute_to_class(cls, name, private_only=True)
        setattr(cls, name, self)

    def __get__(self, instance, instance_type=None):
        return getattr(instance, self.db_column)


class AliasSerializerMixin:
    def serialize(self, queryset, *, stream=None, fields=None, use_natural_foreign_keys=False,  # noqa: MC0001
                  use_natural_primary_keys=False, progress_output=None, object_count=0, **options):
        """
        Serialize a queryset.
        """
        self.options = options

        self.stream = stream if stream is not None else self.stream_class()
        self.selected_fields = fields
        self.use_natural_foreign_keys = use_natural_foreign_keys
        self.use_natural_primary_keys = use_natural_primary_keys
        progress_bar = self.progress_class(progress_output, object_count)

        self.start_serialization()
        self.first = True
        for count, obj in enumerate(queryset, start=1):
            self.start_object(obj)
            # Use the concrete parent class' _meta instead of the object's _meta
            # This is to avoid local_fields problems for proxy models. Refs #17717.
            concrete_model = obj._meta.concrete_model
            for field in concrete_model._meta.fields:  # local_fields -> fields to support AliasField
                if field.serialize:
                    if field.remote_field is None:
                        if self.selected_fields is None or field.attname in self.selected_fields:
                            self.handle_field(obj, field)
                    else:
                        if self.selected_fields is None or field.attname[:-3] in self.selected_fields:
                            self.handle_fk_field(obj, field)
            for field in concrete_model._meta.many_to_many:
                if field.serialize:
                    if self.selected_fields is None or field.attname in self.selected_fields:
                        self.handle_m2m_field(obj, field)
            self.end_object(obj)
            progress_bar.update(count)
            if self.first:
                self.first = False
        self.end_serialization()
        return self.getvalue()


def send_templated_email(template, subject, context, recipients, sender=None):
    request = context.get('request', None)
    send_by = sender if sender else settings.DEFAULT_FROM_EMAIL
    email_body = render_to_string(template, context=context, request=request)
    email = EmailMessage(subject, email_body, send_by, recipients)
    email.content_subtype = 'html'
    email.send()


def get_user(request=None, instance=None):

    if request:
        return request.user.id

    if instance:
        if hasattr(instance, 'updated_by'):
            return instance.updated_by
        for related in RELATED_TO_LOCATION:
            if hasattr(instance, related):
                return getattr(instance, related).updated_by

    return None


def _model_to_dict(model):
    return json.loads(serialize("json", [model]))[0]["fields"]


class TxmHistoricalRecords(HistoricalRecords):

    def _get_history_user_fields(self):
        if self.user_id_field:
            # We simply track the updated_by field
            history_user_fields = {
                "history_user": models.CharField(null=True, blank=True, max_length=36),
            }
        else:
            history_user_fields = {}

        return history_user_fields


class TxmHistoricalChanges:
    def __init__(self, new_obj):
        self.obj = new_obj

    def diff_against(self, old_history):
        if self.obj is not None and old_history is not None:
            if not isinstance(old_history, type(self.obj)):
                raise TypeError(
                    f"unsupported type(s) for diffing: '{type(self.obj)}' and '{type(old_history)}'")

        changes = []
        changed_fields = []
        if hasattr(self.obj, 'instance'):
            current_values = _model_to_dict(self.obj.instance)
        else:
            current_values = _model_to_dict(self.obj)

        if not old_history:
            old_values = {f: None for f in current_values.keys()}
        else:
            old_values = _model_to_dict(old_history.instance)

        for field, new_value in current_values.items():
            if field in old_values:
                old_value = old_values[field]
                if old_value != new_value:
                    change = ModelChange(field, old_value, new_value)
                    changes.append(change)
                    changed_fields.append(field)

        return ModelDelta(changes, changed_fields, old_history, self.obj)
