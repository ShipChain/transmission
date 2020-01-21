import json
import logging
from string import Template

from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Q
from django.http import HttpResponse
from django.utils.decorators import method_decorator
from django_filters.rest_framework import DjangoFilterBackend
from fancy_cache import cache_page
from influxdb_metrics.loader import log_metric
from rest_framework import viewsets, permissions, status, filters, mixins, renderers
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView
from shipchain_common.authentication import get_jwt_from_request
from shipchain_common.exceptions import RPCError
from shipchain_common.pagination import CustomResponsePagination
from shipchain_common.utils import send_templated_email

from apps.jobs.models import JobState
from apps.permissions import owner_access_filter, get_owner_id
from .filters import ShipmentFilter, SHIPMENT_SEARCH_FIELDS
from .geojson import render_filtered_point_features
from .iot_client import DeviceAWSIoTClient
from .models import Shipment, TrackingData, PermissionLink
from .permissions import IsOwnerOrShared, IsShipmentOwner
from .serializers import ShipmentSerializer, ShipmentCreateSerializer, ShipmentUpdateSerializer, ShipmentTxSerializer, \
    TrackingDataSerializer, UnvalidatedTrackingDataSerializer, TrackingDataToDbSerializer, \
    PermissionLinkSerializer, PermissionLinkCreateSerializer, ChangesDiffSerializer, DevicesQueryParamsSerializer, \
    ShipmentActionRequestSerializer
from .tasks import tracking_data_update

LOG = logging.getLogger('transmission')


class ShipmentViewSet(viewsets.ModelViewSet):
    queryset = Shipment.objects.all()
    serializer_class = ShipmentSerializer
    permission_classes = ((IsOwnerOrShared,) if settings.PROFILES_ENABLED
                          else (permissions.AllowAny,))
    filter_backends = (filters.SearchFilter, filters.OrderingFilter, DjangoFilterBackend,)
    filterset_class = ShipmentFilter
    search_fields = SHIPMENT_SEARCH_FIELDS
    ordering_fields = ('updated_at', 'created_at', 'pickup_est', 'delivery_est')
    http_method_names = ['get', 'post', 'delete', 'patch']

    def get_queryset(self):
        queryset = self.queryset
        if settings.PROFILES_ENABLED:
            permission_link = self.request.query_params.get('permission_link', None)
            if permission_link:
                try:
                    permission_link_obj = PermissionLink.objects.get(pk=permission_link)
                except ObjectDoesNotExist:
                    LOG.warning(f'User: {self.request.user}, is trying to access a shipment with permission link: '
                                f'{permission_link}')
                    raise PermissionDenied('No permission link found.')
                queryset = queryset.filter(owner_access_filter(self.request) | Q(pk=permission_link_obj.shipment.pk))
            elif self.detail:
                return queryset
            else:
                queryset = queryset.filter(owner_access_filter(self.request))

        for key, value in self.request.query_params.items():
            if key.startswith('customer_fields__'):
                try:
                    value = json.loads(value)
                except ValueError:
                    pass
                queryset = queryset.filter(**{key: value})

        return queryset

    def perform_create(self, serializer):
        if settings.PROFILES_ENABLED:
            background_data_hash_interval = self.request.user.token.get('background_data_hash_interval',
                                                                        settings.DEFAULT_BACKGROUND_DATA_HASH_INTERVAL)
            manual_update_hash_interval = self.request.user.token.get('manual_update_hash_interval',
                                                                      settings.DEFAULT_MANUAL_UPDATE_HASH_INTERVAL)
            created = serializer.save(owner_id=get_owner_id(self.request), updated_by=self.request.user.id,
                                      background_data_hash_interval=background_data_hash_interval,
                                      manual_update_hash_interval=manual_update_hash_interval)
        else:
            created = serializer.save(background_data_hash_interval=settings.DEFAULT_BACKGROUND_DATA_HASH_INTERVAL,
                                      manual_update_hash_interval=settings.DEFAULT_MANUAL_UPDATE_HASH_INTERVAL)
        return created

    def perform_update(self, serializer):
        return serializer.save(updated_by=self.request.user.id)

    def create(self, request, *args, **kwargs):
        """
        Create a Shipment object and make Async Request to Engine
        """
        LOG.debug(f'Creating a shipment object.')
        log_metric('transmission.info', tags={'method': 'shipments.create', 'module': __name__})
        # Create Shipment
        serializer = ShipmentCreateSerializer(data=request.data, context={'auth': get_jwt_from_request(request)})
        serializer.is_valid(raise_exception=True)

        shipment = self.perform_create(serializer)
        async_job = shipment.asyncjob_set.all()[:1]

        response = ShipmentTxSerializer(shipment)
        if async_job:
            LOG.debug(f'AsyncJob created with id {async_job[0].id}.')
            response.instance.async_job_id = async_job[0].id

        return Response(response.data, status=status.HTTP_202_ACCEPTED)

    @method_decorator(cache_page(60 * 60, remember_all_urls=True))  # Cache responses for 1 hour
    @action(detail=True, methods=['get'], permission_classes=(IsOwnerOrShared,))
    def tracking(self, request, version, pk):
        """
                Retrieve tracking data from db
                """
        LOG.debug(f'Retrieve tracking data for a shipment {pk}.')
        log_metric('transmission.info', tags={'method': 'shipments.tracking', 'module': __name__})
        shipment = Shipment.objects.get(pk=pk)

        # TODO: re-implement device/shipment authorization for tracking data

        tracking_data = TrackingData.objects.filter(shipment__id=shipment.id)

        if tracking_data.exists():
            response = Template('{"data": $geojson}').substitute(
                geojson=render_filtered_point_features(shipment, tracking_data)
            )
            httpresponse = HttpResponse(content=response,
                                        content_type='application/vnd.api+json')
            return httpresponse

        raise NotFound("No tracking data found for Shipment.")

    def update(self, request, *args, **kwargs):
        """
        Update the shipment with new details, overwriting the built-in method
        """
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        LOG.debug(f'Updating shipment {instance.id} with new details.')
        log_metric('transmission.info', tags={'method': 'shipments.update', 'module': __name__})

        serializer = ShipmentUpdateSerializer(instance, data=request.data, partial=partial,
                                              context={'auth': get_jwt_from_request(request)})
        serializer.is_valid(raise_exception=True)

        shipment = self.perform_update(serializer)
        async_jobs = shipment.asyncjob_set.filter(state__in=[JobState.PENDING, JobState.RUNNING])
        response = ShipmentTxSerializer(shipment)

        response.instance.async_job_id = async_jobs.latest('created_at').id if async_jobs else None

        return Response(response.data, status=status.HTTP_202_ACCEPTED)


class DeviceViewSet(viewsets.ViewSet):
    permission_classes = permissions.AllowAny
    serializer_class = PermissionLinkSerializer

    @action(detail=True, methods=['post'], permission_classes=(permissions.AllowAny,))
    def tracking(self, request, version, pk):
        LOG.debug(f'Adding tracking data by device with id: {pk}.')
        log_metric('transmission.info', tags={'method': 'devices.tracking', 'module': __name__})

        shipment = Shipment.objects.filter(device_id=pk).first()

        if not shipment:
            LOG.debug(f'No shipment found associated to device: {pk}')
            raise PermissionDenied('No shipment found associated to device.')

        data = request.data
        serializer = (UnvalidatedTrackingDataSerializer if settings.ENVIRONMENT in ('LOCAL', 'INT')
                      else TrackingDataSerializer)

        if not isinstance(data, list):
            LOG.debug(f'Adding tracking data for device: {pk} for shipment: {shipment.id}')
            serializer = serializer(data=data, context={'shipment': shipment})
            serializer.is_valid(raise_exception=True)
            tracking_data = [serializer.validated_data]
        else:
            LOG.debug(f'Adding bulk tracking data for device: {pk} shipment: {shipment.id}')
            serializer = serializer(data=data, context={'shipment': shipment}, many=True)
            serializer.is_valid(raise_exception=True)
            tracking_data = serializer.validated_data

        for data in tracking_data:
            payload = data['payload']

            # Add tracking data to shipment via Engine RPC
            tracking_data_update.delay(shipment.id, payload)

            # Cache tracking data to db
            tracking_model_serializer = TrackingDataToDbSerializer(data=payload, context={'shipment': shipment,
                                                                                          'device': shipment.device})
            tracking_model_serializer.is_valid(raise_exception=True)
            tracking_model_serializer.save()

        return Response(status=status.HTTP_204_NO_CONTENT)


class PermissionLinkViewSet(mixins.CreateModelMixin,
                            mixins.DestroyModelMixin,
                            mixins.ListModelMixin,
                            viewsets.GenericViewSet):

    queryset = PermissionLink.objects.all()
    permission_classes = ((IsShipmentOwner, ) if settings.PROFILES_ENABLED
                          else (permissions.AllowAny,))
    serializer_class = PermissionLinkSerializer
    resource_name = 'PermissionLink'

    def get_queryset(self):
        return self.queryset.filter(shipment_id=self.kwargs['shipment_pk'])

    def create(self, request, *args, **kwargs):
        """
        Creates a link to grant permission to read shipments
        """
        shipment_id = kwargs['shipment_pk']
        LOG.debug(f'Creating permission link for shipment {shipment_id}')
        log_metric('transmission.info', tags={'method': 'shipments.create_permission_link', 'module': __name__})

        create_serializer = PermissionLinkCreateSerializer(data=request.data)
        create_serializer.is_valid(raise_exception=True)

        emails = None
        if 'emails' in create_serializer.validated_data:
            emails = create_serializer.validated_data.pop('emails')

        permission_link = create_serializer.save(shipment_id=shipment_id)

        if settings.PROFILES_ENABLED and emails:
            LOG.debug(f'Emailing permission link: {permission_link.id}')
            username = request.user.username
            protocol = 'https' if request.is_secure() else 'http'
            subject = f'{username} shared a shipment details page with you.'
            email_context = {
                'username': username,
                'link': f'{protocol}://{settings.FRONTEND_DOMAIN}/shipments/{shipment_id}/'
                        f'?permission_link={permission_link.id}',
                'request': request
            }

            send_templated_email('email/shipment_link.html', subject, email_context, emails)

        return Response(self.get_serializer(permission_link).data, status=status.HTTP_201_CREATED)


class ShipmentHistoryListView(viewsets.GenericViewSet):
    http_method_names = ('get', )
    permission_classes = ((IsOwnerOrShared,) if settings.PROFILES_ENABLED else (permissions.AllowAny,))
    pagination_class = CustomResponsePagination
    renderer_classes = (renderers.JSONRenderer, )

    def list(self, request, *args, **kwargs):
        LOG.debug(f'Listing shipment history for shipment with id: {kwargs["shipment_pk"]}.')
        log_metric('transmission.info', tags={'method': 'shipment.history', 'module': __name__})

        shipment = Shipment.objects.get(id=kwargs['shipment_pk'])

        serializer = ChangesDiffSerializer(shipment.history.all(), request, kwargs['shipment_pk'])

        queryset = serializer.filter_queryset(serializer.historical_queryset)

        paginator = self.pagination_class()
        page = paginator.paginate_queryset(queryset, self.request, view=self)
        if page is not None:
            return paginator.get_paginated_response(serializer.get_data(page))

        return Response(serializer.get_data(queryset))


class ShipmentActionsView(APIView):
    resource_name = 'Shipment'
    permission_classes = ((IsShipmentOwner,) if settings.PROFILES_ENABLED else (permissions.AllowAny,))

    def post(self, request, *args, **kwargs):
        LOG.debug(f'Performing action on shipment with id: {kwargs["shipment_pk"]}.')
        log_metric('transmission.info', tags={'method': 'shipment.action', 'module': __name__})

        shipment = Shipment.objects.get(id=kwargs['shipment_pk'])
        serializer = ShipmentActionRequestSerializer(data=request.data, context={'shipment': shipment})
        serializer.is_valid(raise_exception=True)

        method = serializer.validated_data.pop('action_type')
        method.value(shipment, **serializer.validated_data)
        shipment.save()

        return Response(ShipmentSerializer(shipment).data)


class ListDevicesStatus(APIView):
    http_method_names = ['get', ]
    permission_classes = (permissions.IsAuthenticated, )
    pagination_class = CustomResponsePagination
    renderer_classes = (renderers.JSONRenderer,)

    def get(self, request, *args, **kwargs):
        owner_id = get_owner_id(request)

        LOG.debug(f'Listing devices for owner with id: {owner_id}.')
        log_metric('transmission.info', tags={'method': 'devices.list', 'module': __name__})

        if not settings.IOT_THING_INTEGRATION:
            raise RPCError('IoT Integration is not set up in this environment.',
                           status_code=status.HTTP_501_NOT_IMPLEMENTED)

        iot_client = DeviceAWSIoTClient()

        serializer = DevicesQueryParamsSerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)

        devices = iot_client.get_list_owner_devices(owner_id, serializer.validated_data)

        paginator = self.pagination_class()
        page = paginator.paginate_queryset(devices, request, view=self)
        if page is not None:
            return paginator.get_paginated_response(page)
        return Response(devices, status=status.HTTP_200_OK)
