from django.db.models.aggregates import Avg, Count, Max, Min, StdDev, Sum, Variance
from functools import partial
from enumfields import Enum

from django.conf import settings

from rest_framework import exceptions
from shipchain_common.authentication import get_jwt_from_request
from shipchain_common.exceptions import Custom500Error


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


class S3PreSignedMixin:
    def get_content_type(self, extension):
        extension = extension if extension.startswith('.') else f'.{extension}'
        content_type = settings.MIME_TYPE_MAP.get(extension)
        if not content_type:
            raise exceptions.ValidationError(f'Unrecognized file type: {extension}')
        return content_type

    def get_presigned_s3(self, obj):
        content_type = self.get_content_type(obj.file_type.name.lower())

        pre_signed_post = settings.S3_CLIENT.generate_presigned_post(
            Bucket=self._s3_bucket,
            Key=obj.s3_key,
            Fields={"acl": "private", "Content-Type": content_type},
            Conditions=[
                {"acl": "private"},
                {"Content-Type": content_type},
                ["content-length-range", 0, settings.S3_MAX_BYTES]
            ],
            ExpiresIn=settings.S3_URL_LIFE
        )
        return pre_signed_post


class UploadStatus(Enum):
    PENDING = 0
    COMPLETE = 1
    FAILED = 2

    class Labels:
        PENDING = 'PENDING'
        COMPLETE = 'COMPLETE'
        FAILED = 'FAILED'


class Aggregates(Enum):
    Avg = partial(Avg)
    Count = partial(Count)
    Max = partial(Max)
    Min = partial(Min)
    StdDev = partial(StdDev)
    Sum = partial(Sum)
    Variance = partial(Variance)


def retrieve_profiles_wallet_ids(request):
    response = settings.REQUESTS_SESSION.get(
        f'{settings.PROFILES_URL}/api/v1/wallet?page_size=9999&is_active',
        headers={'Authorization': 'JWT {}'.format(get_jwt_from_request(request))}
    )
    if not response.ok:
        raise Custom500Error(detail='Invalid response from profiles', status_code=response.status_code)

    return [data['id'] for data in response.json()['data']]
