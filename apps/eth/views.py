import logging

from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from rest_framework import mixins, viewsets, parsers, status, renderers, permissions
from rest_framework.response import Response
from rest_framework_json_api import renderers as jsapi_renderers

from apps.eth.models import EthAction, Event
from apps.eth.serializers import EventSerializer, EthActionSerializer

from .permissions import IsOwner

LOG = logging.getLogger('transmission')


class EventViewSet(mixins.CreateModelMixin,
                   viewsets.GenericViewSet):
    """
    Handles Event callbacks from Engine
    """
    queryset = Event.objects.all()
    serializer_class = EventSerializer
    parser_classes = (parsers.JSONParser,)
    renderer_classes = (renderers.JSONRenderer, jsapi_renderers.JSONRenderer)
    # TODO: Restrict for Engine
    permission_classes = (permissions.AllowAny,)

    def create(self, request, *args, **kwargs):

        is_many = isinstance(request.data, list)

        if not is_many:
            serializer = EventSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)

            try:
                action = EthAction.objects.get(transaction_hash=serializer.data['transaction_hash'])
            except ObjectDoesNotExist:
                action = None
                # TODO: Events without Receipt metric reporting
                LOG.info(f"Non-EthAction Event processed "
                         f"Tx: {serializer.data['transaction_hash']}")

            Event.objects.create(**serializer.data, eth_action=action)

        else:
            serializer = EventSerializer(data=request.data, many=True)
            serializer.is_valid(raise_exception=True)

            for event in serializer.data:
                try:
                    action = EthAction.objects.get(transaction_hash=event['transaction_hash'])
                except ObjectDoesNotExist:
                    action = None
                    # TODO: Events without Receipt metric reporting
                    LOG.info(f"Non-EthAction Event processed "
                             f"Tx: {event['transaction_hash']}")

                Event.objects.create(**event, eth_action=action)

        return Response(status=status.HTTP_204_NO_CONTENT)


class TransactionViewSet(mixins.RetrieveModelMixin,
                         viewsets.GenericViewSet):
    """
    Get tx details for a transaction hash
    """
    queryset = EthAction.objects.all()
    serializer_class = EthActionSerializer
    permission_classes = (permissions.IsAuthenticated, IsOwner) if settings.PROFILES_URL else (permissions.AllowAny,)

    def get_queryset(self):
        queryset = self.queryset
        if settings.PROFILES_URL:
            queryset = queryset.filter(ethlistener__shipments__owner_id=self.request.user.id)
        return queryset
