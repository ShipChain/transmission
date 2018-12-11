from rest_framework_json_api import serializers
from enumfields.drf import EnumSupportSerializerMixin

from apps.utils import UpperEnumField
from .models import AsyncJob, Message, MessageType, JobState


class MessageSerializer(EnumSupportSerializerMixin, serializers.ModelSerializer):
    type = UpperEnumField(MessageType, lenient=True, ints_as_names=True)

    class Meta:
        model = Message
        exclude = ('async_job',)


class AsyncJobSerializer(EnumSupportSerializerMixin, serializers.ModelSerializer):
    message_set = serializers.ResourceRelatedField(queryset=Message.objects, many=True)
    state = UpperEnumField(JobState, lenient=True, ints_as_names=True)

    class Meta:
        model = AsyncJob
        exclude = ('listeners', 'wallet_lock_token')

    included_serializers = {
        'message_set': MessageSerializer
    }

    class JSONAPIMeta:
        included_resources = ['message_set']
