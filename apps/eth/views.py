import logging

from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist, MultipleObjectsReturned
from django.db.models import Q
from django_filters.rest_framework import DjangoFilterBackend
from influxdb_metrics.loader import log_metric
from rest_framework import mixins, viewsets, parsers, status, renderers, permissions, filters
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework_json_api import renderers as jsapi_renderers, serializers
from shipchain_common.authentication import EngineRequest, get_jwt_from_request
from shipchain_common.exceptions import RPCError

from apps.eth.models import EthAction, Event
from apps.eth.serializers import EventSerializer, EthActionSerializer
from apps.permissions import get_owner_id, shipment_owner_access_filter
from apps.shipments.models import PermissionLink
from apps.shipments.permissions import IsListenerOwner

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

    @staticmethod
    def _process_event(event, project):
        if project == 'LOAD':
            try:
                action = EthAction.objects.get(transaction_hash=event['transaction_hash'])
                Event.objects.get_or_create(defaults=event, eth_action=action, log_index=event['log_index'])
            except RPCError as exc:
                LOG.info(f"Engine RPC error processing event {event['transaction_hash']}: {exc}")
            except MultipleObjectsReturned as exc:
                LOG.info(f"MultipleObjectsReturned during get/get_or_create for event {event['transaction_hash']}: "
                         f"{exc}")
            except ObjectDoesNotExist:
                LOG.info(f"Non-EthAction Event processed Tx: {event['transaction_hash']}")
                log_metric('transmission.info', tags={'method': 'events.create', 'code': 'non_ethaction_event',
                                                      'module': __name__, 'project': project})
        elif project == 'ShipToken' and event['event_name'] == 'Transfer':
            LOG.info(f"ShipToken Transfer processed Tx: {event['transaction_hash']}")
            log_metric('transmission.info',
                       tags={'method': 'event.transfer', 'module': __name__, 'project': project},
                       fields={'from_address': event['return_values']['from'],
                               'to_address': event['return_values']['to'],
                               'token_amount': float(event['return_values']['value']) / (10 ** 18),
                               'count': 1})
        else:
            LOG.warning(f"Unexpected event {event} found with project: {project}")

    def create(self, request, *args, **kwargs):
        log_metric('transmission.info',
                   tags={'method': 'events.create', 'module': __name__, 'project': request.data['project']})
        LOG.debug('Events create')

        is_many = isinstance(request.data['events'], list)
        serializer = EventSerializer(data=request.data['events'], many=is_many)
        serializer.is_valid(raise_exception=True)

        events = serializer.data if is_many else [serializer.data]

        for event in events:
            self._process_event(event, request.data['project'])

        return Response(status=status.HTTP_204_NO_CONTENT)


class TransactionViewSet(mixins.RetrieveModelMixin,
                         mixins.ListModelMixin,
                         viewsets.GenericViewSet):
    """
    Get tx details for a transaction hash
    """
    queryset = EthAction.objects.all()
    serializer_class = EthActionSerializer
    permission_classes = ((IsListenerOwner, ) if settings.PROFILES_ENABLED else (permissions.AllowAny, ))
    filter_backends = (filters.OrderingFilter, DjangoFilterBackend,)
    ordering_fields = ('updated_at', 'created_at')

    def get_queryset(self):
        log_metric('transmission.info', tags={'method': 'transaction.get_queryset', 'module': __name__})
        LOG.debug('Getting tx details for a transaction hash.')
        queryset = self.queryset
        if settings.PROFILES_ENABLED:
            if 'wallet_id' in self.request.query_params:
                queryset = queryset.filter(Q(shipment__owner_id=get_owner_id(self.request)) |
                                           Q(shipment__shipper_wallet_id=
                                             self.request.query_params.get('wallet_id')) |
                                           Q(shipment__moderator_wallet_id=
                                             self.request.query_params.get('wallet_id')) |
                                           Q(shipment__carrier_wallet_id=
                                             self.request.query_params.get('wallet_id')))
            else:
                permission_link = self.request.query_params.get('permission_link', None)
                if permission_link:
                    try:
                        permission_link_obj = PermissionLink.objects.get(pk=permission_link)
                    except ObjectDoesNotExist:
                        LOG.warning(f'User: {self.request.user}, is trying to access a shipment with permission link: '
                                    f'{permission_link}')
                        raise PermissionDenied('No permission link found.')
                    queryset = queryset.filter(
                        shipment_owner_access_filter(self.request) | Q(shipment__pk=permission_link_obj.shipment.pk)
                    )

        return queryset

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        log_metric('transmission.info', tags={'method': 'transaction.list', 'module': __name__})

        shipment_pk = kwargs.get('shipment_pk', None)
        if shipment_pk:
            LOG.debug(f'Getting transactions for shipment: {shipment_pk}.')

            queryset = queryset.filter(shipment__id=shipment_pk)
        else:
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

                wallet_response = settings.REQUESTS_SESSION.get(
                    f'{settings.PROFILES_URL}/api/v1/wallet/{wallet_id}/?is_active',
                    headers={'Authorization': f'JWT {get_jwt_from_request(request)}'}
                )

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
