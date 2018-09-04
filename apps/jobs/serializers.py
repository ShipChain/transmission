from rest_framework_json_api import serializers
from drf_enum_field.serializers import EnumFieldSerializerMixin
from .models import AsyncJob, Message


class MessageSerializer(EnumFieldSerializerMixin, serializers.ModelSerializer):
    class Meta:
        model = Message
        fields = ('type', 'body', 'created_at')


class AsyncJobSerializer(EnumFieldSerializerMixin, serializers.ModelSerializer):
    message_set = serializers.ResourceRelatedField(queryset=Message.objects, many=True)

    class Meta:
        model = AsyncJob
        exclude = ('listeners',)

    included_serializers = {
        'message_set': MessageSerializer
    }

    class JSONAPIMeta:
        included_resources = ['message_set']
