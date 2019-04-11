import logging
from string import Template

from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist, PermissionDenied
from django.db.models import Q
from django.http import HttpResponse, HttpResponseNotFound
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import viewsets, permissions, status, filters, mixins
from rest_framework.decorators import action
from rest_framework.response import Response
from influxdb_metrics.loader import log_metric

from apps.authentication import get_jwt_from_request
from apps.jobs.models import JobState
from apps.permissions import owner_access_filter, get_owner_id
from .filters import ShipmentFilter
from .geojson import render_point_features
from .models import Shipment, TrackingData, PermissionLink
from .permissions import IsOwnerOrShared, IsShipmentOwner
from .serializers import ShipmentSerializer, ShipmentCreateSerializer, ShipmentUpdateSerializer, ShipmentTxSerializer, \
    TrackingDataSerializer, UnvalidatedTrackingDataSerializer, TrackingDataToDbSerializer, \
    PermissionLinkSerializer
from .tasks import tracking_data_update

LOG = logging.getLogger('transmission')


class ShipmentViewSet(viewsets.ModelViewSet):
    queryset = Shipment.objects.all()
    serializer_class = ShipmentSerializer
    permission_classes = ((IsOwnerOrShared,) if settings.PROFILES_ENABLED
                          else (permissions.AllowAny,))
    filter_backends = (filters.SearchFilter, filters.OrderingFilter, DjangoFilterBackend,)
    filterset_class = ShipmentFilter
    search_fields = ('shippers_reference', 'forwarders_reference')
    ordering_fields = ('modified_at', 'created_at', 'pickup_est', 'delivery_est')
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
        return queryset

    def perform_create(self, serializer):
        if settings.PROFILES_ENABLED:
            created = serializer.save(owner_id=get_owner_id(self.request), updated_by=self.request.user.id)
        else:
            created = serializer.save()
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

    @method_decorator(cache_page(60 * 10, cache='page'))  # Cache responses for 10 minutes
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
            response = Template('{"data": $geojson}').substitute(geojson=render_point_features(shipment, tracking_data))
            httpresponse = HttpResponse(content=response,
                                        content_type='application/vnd.api+json')
            return httpresponse

        return HttpResponseNotFound()

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
        serializer = UnvalidatedTrackingDataSerializer if settings.ENVIRONMENT == 'LOCAL' else TrackingDataSerializer

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
    permission_classes = ((permissions.IsAuthenticated, IsShipmentOwner) if settings.PROFILES_ENABLED
                          else (permissions.AllowAny,))
    serializer_class = PermissionLinkSerializer
    resource_name = 'PermissionLink'

    def get_queryset(self):
        queryset = self.queryset
        if settings.PROFILES_ENABLED:
            queryset.filter(shipment__owner_id=get_owner_id(self.request))
        return queryset

    def create(self, request, *args, **kwargs):
        """
        Creates a link to grant permission to read shipments
        """
        LOG.debug('Creating permission link for shipment.')
        log_metric('transmission.info', tags={'method': 'shipments.create_permission_link', 'module': __name__})

        serializer = PermissionLinkSerializer(data=request.data, context={'shipment_id': kwargs['shipment_pk']})
        serializer.is_valid(raise_exception=True)

        permission_link = PermissionLink.objects.create(**serializer.validated_data)

        return Response(PermissionLinkSerializer(permission_link).data, status=status.HTTP_201_CREATED)
