import logging

from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from rest_framework import mixins, viewsets, parsers, status, renderers, permissions
from rest_framework.response import Response
from rest_framework_json_api import renderers as jsapi_renderers, serializers
from influxdb_metrics.loader import log_metric

from apps.authentication import EngineRequest
from apps.eth.models import EthAction, Event, TransactionReceipt
from apps.eth.permissions import ProfilesRequest
from apps.eth.serializers import EventSerializer, EthActionSerializer, TransactionReceiptSerializer

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
    permission_classes = (EngineRequest,)

    def create(self, request, *args, **kwargs):
        log_metric('transmission.info', tags={'method': 'events.create', 'module': __name__})
        LOG.debug('Events create')

        is_many = isinstance(request.data, list)

        if not is_many:
            LOG.debug('Event is_many is false')
            serializer = EventSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)

            try:
                LOG.debug(f'Finding contract receipt for tx hash: {serializer.data["transaction_hash"]}')
                action = EthAction.objects.get(transaction_hash=serializer.data['transaction_hash'])
            except ObjectDoesNotExist:
                action = None
                log_metric('transmission.error', tags={'method': 'events.create', 'code': 'object_does_not_exist',
                                                       'module': __name__, 'detail': 'events.is_many is false'})
                LOG.info(f"Non-EthAction Event processed "
                         f"Tx: {serializer.data['transaction_hash']}")

            Event.objects.get_or_create(**serializer.data, eth_action=action)

        else:
            LOG.debug('Events is_many is true')
            serializer = EventSerializer(data=request.data, many=True)
            serializer.is_valid(raise_exception=True)

            for event in serializer.data:
                try:
                    LOG.debug(f'Finding contract receipt for tx hash: {event["transaction_hash"]}')
                    action = EthAction.objects.get(transaction_hash=event['transaction_hash'])
                except ObjectDoesNotExist:
                    action = None
                    log_metric('transmission.error', tags={'method': 'events.create', 'code': 'object_does_not_exist',
                                                           'module': __name__, 'detail': 'events.is_many is true'})
                    LOG.info(f"Non-EthAction Event processed "
                             f"Tx: {event['transaction_hash']}")

                Event.objects.get_or_create(**event, eth_action=action)

        return Response(status=status.HTTP_204_NO_CONTENT)


class TransactionViewSet(mixins.RetrieveModelMixin,
                         viewsets.GenericViewSet):
    """
    Get tx details for a transaction hash
    """
    queryset = EthAction.objects.all()
    serializer_class = EthActionSerializer
    permission_classes = ((permissions.IsAuthenticated, IsOwner) if settings.PROFILES_ENABLED
                          else (permissions.AllowAny,))

    def get_queryset(self):
        log_metric('transmission.info', tags={'method': 'transaction.get_queryset', 'module': __name__})
        LOG.debug('Getting tx details for a transaction hash.')
        queryset = self.queryset
        if settings.PROFILES_ENABLED:
            queryset = queryset.filter(ethlistener__shipments__owner_id=self.request.user.id)
        return queryset


class TransactionReceiptViewSet(mixins.ListModelMixin,
                                viewsets.GenericViewSet):
    """
    Get all transactions related to wallet
    """
    queryset = TransactionReceipt.objects.all()
    serializer_class = TransactionReceiptSerializer
    permission_classes = (ProfilesRequest, )
    http_method_names = ['get']

    def get_queryset(self):
        log_metric('transmission.info', tags={'method': 'transaction.get_queryset', 'module': __name__})
        LOG.debug('Getting tx details for a transaction hash.')

        queryset = self.queryset

        if not self.request.query_params.get('wallet_address'):
            raise serializers.ValidationError(
                'wallet_addres required in query parameters')

        queryset = queryset.filter(from_address__iexact=self.request.query_params.get('wallet_address'))

        return queryset
