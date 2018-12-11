import logging

from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Q
from rest_framework import mixins, viewsets, parsers, status, renderers, permissions
from rest_framework.response import Response
from rest_framework_json_api import renderers as jsapi_renderers, serializers
from influxdb_metrics.loader import log_metric

from apps.authentication import EngineRequest
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
                         mixins.ListModelMixin,
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
            if 'wallet_id' in self.request.query_params:
                queryset = queryset.filter(Q(ethlistener__shipments__owner_id=self.request.user.id) |
                                           Q(ethlistener__shipments__shippers_wallet_id=
                                             self.request.query_params.get('wallet_id')) |
                                           Q(ethlistener__shipments__moderators_wallet_id=
                                             self.request.query_params.get('wallet_id')) |
                                           Q(ethlistener__shipments__carriers_wallet_id=
                                             self.request.query_params.get('wallet_id')))
            else:
                queryset = queryset.filter(ethlistener__shipments__owner_id=self.request.user.id)

        return queryset

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        log_metric('transmission.info', tags={'method': 'transaction.list', 'module': __name__})
        LOG.debug('Getting tx details filtered by wallet address.')

        if not settings.PROFILES_ENABLED:
            if 'wallet_address' not in self.request.query_params:
                raise serializers.ValidationError(
                    'wallet_address required in query parameters')

            from_address = self.request.query_params.get('wallet_address')

        else:
            if 'wallet_id' not in self.request.query_params:
                raise serializers.ValidationError(
                    'wallet_id required in query parameters')

            wallet_id = self.request.query_params.get('wallet_id')

            wallet_response = settings.REQUESTS_SESSION.get(f'{settings.PROFILES_URL}/api/v1/wallet/{wallet_id}/',
                                                            headers={
                                                                'Authorization': 'JWT {}'.format(request.auth.decode())
                                                            })

            if not wallet_response.status_code == status.HTTP_200_OK:
                raise serializers.ValidationError('Error retrieving Wallet from ShipChain Profiles')

            wallet_details = wallet_response.json()
            from_address = wallet_details['data']['attributes']['address']

        queryset = queryset.filter(transactionreceipt__from_address__iexact=from_address)

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)
