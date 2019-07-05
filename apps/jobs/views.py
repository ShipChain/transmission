import logging

from django.conf import settings
from rest_framework import viewsets, mixins, permissions, parsers, status, renderers
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework_json_api import parsers as jsapi_parsers
from influxdb_metrics.loader import log_metric

from apps.authentication import EngineRequest
from apps.permissions import get_owner_id
from apps.shipments.permissions import IsListenerOwner
from .models import AsyncJob, Message
from .serializers import AsyncJobSerializer, MessageSerializer

LOG = logging.getLogger('transmission')


class JobsViewSet(mixins.ListModelMixin,
                  mixins.RetrieveModelMixin,
                  viewsets.GenericViewSet):
    """
    Manages the state of an AsyncJob
    """
    queryset = AsyncJob.objects.all()
    serializer_class = AsyncJobSerializer
    permission_classes = ((permissions.IsAuthenticated, IsListenerOwner) if settings.PROFILES_ENABLED
                          else (permissions.AllowAny,))
    parser_classes = (parsers.JSONParser, jsapi_parsers.JSONParser)

    def get_queryset(self):
        queryset = self.queryset
        if settings.PROFILES_ENABLED:
            queryset = queryset.filter(shipment__owner_id=get_owner_id(self.request))
        return queryset

    @action(detail=True, methods=['post'],
            permission_classes=[EngineRequest],
            renderer_classes=[renderers.JSONRenderer])
    def message(self, request, version, pk):
        LOG.debug(f'Jobs message called.')
        log_metric('transmission.info', tags={'method': 'jobs.message', 'module': __name__})

        serializer = MessageSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        Message.objects.get_or_create(**serializer.data, async_job_id=pk)

        return Response(status=status.HTTP_204_NO_CONTENT)
