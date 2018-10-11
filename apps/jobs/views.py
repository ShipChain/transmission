import logging

from rest_framework import viewsets, mixins, parsers, permissions, status, renderers
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework_json_api import parsers as jsapi_parsers
from influxdb_metrics.loader import log_metric

from .models import AsyncJob
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
    parser_classes = (parsers.JSONParser, jsapi_parsers.JSONParser)

    @action(detail=True, methods=['post'],
            permission_classes=[permissions.AllowAny],
            renderer_classes=[renderers.JSONRenderer])
    def message(self, request, version, pk):
        LOG.debug(f'Jobs message called.')
        log_metric('transmission.info', tags={'method': 'jobs.message', 'module': __name__})

        serializer = MessageSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        serializer.save(async_job_id=pk)

        return Response(status=status.HTTP_204_NO_CONTENT)
