import logging

from django.conf import settings
from rest_framework import viewsets, permissions, status, exceptions
from rest_framework.decorators import action
from rest_framework.response import Response
from influxdb_metrics.loader import log_metric

from .geojson import build_line_string_feature, build_point_features, build_feature_collection
from .models import Shipment, Location, TrackingData
from .permissions import IsOwner, IsUserOrDevice
from .serializers import ShipmentSerializer, ShipmentCreateSerializer, ShipmentUpdateSerializer, ShipmentTxSerializer,\
    LocationSerializer, TrackingDataSerializer, UnvalidatedTrackingDataSerializer, TrackingDataToDbSerializer

LOG = logging.getLogger('transmission')


class ShipmentViewSet(viewsets.ModelViewSet):
    queryset = Shipment.objects.all()
    serializer_class = ShipmentSerializer
    permission_classes = ((permissions.IsAuthenticated, IsOwner) if settings.PROFILES_ENABLED
                          else (permissions.AllowAny,))
    http_method_names = ['get', 'post', 'delete', 'patch']

    def get_queryset(self):
        queryset = self.queryset
        if settings.PROFILES_ENABLED:
            queryset = queryset.filter(owner_id=self.request.user.id)
        return queryset

    def perform_create(self, serializer):
        if settings.PROFILES_ENABLED:
            created = serializer.save(owner_id=self.request.user.id)
        else:
            created = serializer.save()
        return created

    def perform_update(self, serializer):
        return serializer.save()

    def data_to_db(self, payload):
        data = {}
        data.update(payload['position'])
        payload.pop('position')
        data.update(payload)

        return data

    def create(self, request, *args, **kwargs):
        """
        Create a Shipment object and make Async Request to Engine
        """
        LOG.debug(f'Creating a shipment object.')
        log_metric('transmission.info', tags={'method': 'shipments.create', 'module': __name__})
        # Create Shipment
        serializer = ShipmentCreateSerializer(data=request.data, context={'auth': request.auth})
        serializer.is_valid(raise_exception=True)

        shipment = self.perform_create(serializer)
        async_job = shipment.asyncjob_set.all()[:1]

        response = ShipmentTxSerializer(shipment)
        if async_job:
            LOG.debug(f'AsyncJob created with id {async_job[0].id}.')
            response.instance.async_job_id = async_job[0].id

        return Response(response.data, status=status.HTTP_202_ACCEPTED)

    def get_tracking_data(self, request, version, pk):
        """
        Retrieve tracking data from db
        """
        LOG.debug(f'Retrieve tracking data for a shipment {pk}.')
        log_metric('transmission.info', tags={'method': 'shipments.tracking', 'module': __name__})
        shipment = Shipment.objects.get(pk=pk)

        # TODO: re-implement device/shipment authorization for tracking data

        tracking_data = TrackingData.objects.filter(shipment__id=shipment.id)

        if 'as_line' in request.query_params:
            all_features = build_line_string_feature(shipment, tracking_data)
        elif 'as_point' in request.query_params:
            all_features = build_point_features(shipment, tracking_data)
        else:
            all_features = []
            all_features += build_line_string_feature(shipment, tracking_data)
            all_features += build_point_features(shipment, tracking_data)

        feature_collection = build_feature_collection(all_features)

        return Response(data=feature_collection, status=status.HTTP_200_OK)

    def add_tracking_data(self, request, version, pk):
        shipment = Shipment.objects.get(pk=pk)

        # Ensure payload is a valid JWS
        if settings.ENVIRONMENT == 'LOCAL':
            serializer = UnvalidatedTrackingDataSerializer(data=request.data, context={'shipment': shipment})
        else:
            serializer = TrackingDataSerializer(data=request.data, context={'shipment': shipment})
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data['payload']

        # Add tracking data to shipment via Engine RPC
        from .tasks import tracking_data_update
        tracking_data_update.delay(shipment.id, payload)

        # Cache tracking data to db
        tracking_model_serializer = TrackingDataToDbSerializer(data=self.data_to_db(payload),
                                                               context={'shipment': shipment})

        tracking_model_serializer.is_valid()
        LOG.debug(f'Added tracking data for Shipment: {shipment.id}')
        tracking_model_serializer.save()

        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=['get', 'post'], permission_classes=(IsUserOrDevice,))
    def tracking(self, request, version, pk):
        if request.method == 'GET':
            return self.get_tracking_data(request, version, pk)
        if request.method == 'POST':
            return self.add_tracking_data(request, version, pk)
        raise exceptions.MethodNotAllowed(request.method)

    def update(self, request, *args, **kwargs):
        """
        Update the shipment with new details, overwriting the built-in method
        """
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        LOG.debug(f'Updating shipment {instance} with new details.')
        log_metric('transmission.info', tags={'method': 'shipments.update', 'module': __name__})

        serializer = ShipmentUpdateSerializer(instance, data=request.data, partial=partial,
                                              context={'auth': request.auth})
        serializer.is_valid(raise_exception=True)

        shipment = self.perform_update(serializer)
        async_job = shipment.asyncjob_set.latest('created_at')
        response = ShipmentTxSerializer(shipment)
        LOG.debug(f'Asyncjob created with id {async_job.id}.')
        if async_job:
            response.instance.async_job_id = async_job.id

        return Response(response.data, status=status.HTTP_202_ACCEPTED)


class LocationViewSet(viewsets.ModelViewSet):
    queryset = Location.objects.all()
    serializer_class = LocationSerializer
    # TODO: Clarify/Solidify the permissions for Locations w/ respect to owner_id
    permission_classes = ((permissions.IsAuthenticated, IsOwner) if settings.PROFILES_ENABLED
                          else (permissions.AllowAny,))
    http_method_names = ['get', 'post', 'delete', 'patch']

    def get_queryset(self):
        queryset = self.queryset
        if settings.PROFILES_ENABLED:
            queryset = queryset.filter(owner_id=self.request.user.id)
        return queryset

    def perform_create(self, serializer):
        if settings.PROFILES_ENABLED:
            created = serializer.save(owner_id=self.request.user.id)
        else:
            created = serializer.save()
        return created

    def perform_update(self, serializer):
        return serializer.save()

    def create(self, request, *args, **kwargs):
        """
        Create a Location object
        """
        # Create Location
        serializer = LocationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        LOG.debug(f'Creating a location object.')
        log_metric('transmission.info', tags={'method': 'location.create', 'module': __name__})

        location = self.perform_create(serializer)

        return Response(LocationSerializer(location).data,
                        status=status.HTTP_201_CREATED,)
