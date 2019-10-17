from rest_framework_json_api import serializers
from enumfields.drf import EnumSupportSerializerMixin

from shipchain_common.utils import UpperEnumField, EnumIntegerFieldLabel
from .models import AsyncJob, Message, MessageType, JobState, AsyncActionType, AsyncAction


class MessageSerializer(EnumSupportSerializerMixin, serializers.ModelSerializer):
    type = UpperEnumField(MessageType, lenient=True, ints_as_names=True)

    class Meta:
        model = Message
        exclude = ('async_job',)


class ActionSerializer(EnumSupportSerializerMixin, serializers.ModelSerializer):
    action_type = EnumIntegerFieldLabel(AsyncActionType)

    class Meta:
        model = AsyncAction
        exclude = ('async_job',)


class AsyncJobSerializer(EnumSupportSerializerMixin, serializers.ModelSerializer):
    message_set = serializers.ResourceRelatedField(queryset=Message.objects, many=True)
    actions = serializers.ResourceRelatedField(queryset=AsyncAction.objects, many=True)
    state = UpperEnumField(JobState, lenient=True, ints_as_names=True)

    class Meta:
        model = AsyncJob
        exclude = ('wallet_lock_token',)
        include = {
            "actions": ActionSerializer(),
        }

    included_serializers = {
        'message_set': MessageSerializer,
        'actions': ActionSerializer,
    }

    class JSONAPIMeta:
        included_resources = ['message_set', 'actions']
