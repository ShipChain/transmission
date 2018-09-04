from django.conf import settings
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response

from .geojson import build_line_string_feature, build_point_features, build_feature_collection
from .models import Shipment
from .permissions import IsOwner
from .rpc import ShipmentRPCClient
from .serializers import ShipmentSerializer, ShipmentCreateSerializer, \
    ShipmentUpdateSerializer, ShipmentTxSerializer


class ShipmentViewSet(viewsets.ModelViewSet):
    queryset = Shipment.objects.all()
    serializer_class = ShipmentSerializer
    permission_classes = (permissions.IsAuthenticated, IsOwner) if settings.PROFILES_URL else (permissions.AllowAny,)

    def get_queryset(self):
        queryset = self.queryset
        if settings.PROFILES_URL:
            queryset = queryset.filter(owner_id=self.request.user.id)
        return queryset

    def perform_create(self, serializer):
        if settings.PROFILES_URL:
            created = serializer.save(owner_id=self.request.user.id)
        else:
            created = serializer.save()
        return created

    def perform_update(self, serializer):
        return serializer.save()

    def create(self, request, *args, **kwargs):
        """
        Create a Shipment object and make Async Request to Engine
        """
        # Create Shipment
        serializer = ShipmentCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        shipment = self.perform_create(serializer)
        async_job = shipment.asyncjob_set.all()[:1]

        response = ShipmentTxSerializer(shipment)
        if async_job:
            response.instance.async_job_id = async_job[0].id

        return Response(response.data, status=status.HTTP_202_ACCEPTED)

    @action(detail=True, methods=['get'])
    def tracking(self, request, version, pk=None):
        """
        Retrieve tracking data for this Shipment after checking permissions with Profiles
        """
        shipment = Shipment.objects.get(pk=pk)

        # TODO: re-implement device/shipment authorization for tracking data

        rpc_client = ShipmentRPCClient()
        tracking_data = rpc_client.get_tracking_data(shipment.storage_credentials_id,
                                                     shipment.shipper_wallet_id,
                                                     shipment.vault_id)

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

    def update(self, request, *args, **kwargs):
        """
        Update the shipment with new details, overwriting the built-in method
        """
        partial = kwargs.pop('partial', False)
        instance = self.get_object()

        serializer = ShipmentUpdateSerializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)

        shipment = self.perform_update(serializer)
        async_job = shipment.asyncjob_set.all()[:1]  # TODO: be sure to filter to the latest one, handle race cond.

        response = ShipmentTxSerializer(shipment)
        if async_job:
            response.instance.async_job_id = async_job[0].id

        return Response(response.data, status=status.HTTP_202_ACCEPTED)
