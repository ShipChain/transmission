"""
Copyright 2019 ShipChain, Inc.

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""

import logging

from django.conf import settings
from influxdb_metrics.loader import log_metric
from rest_framework import viewsets, permissions, status, mixins
from rest_framework.response import Response
from shipchain_common.utils import send_templated_email

from apps.permissions import ShipmentExists, IsOwnerShipperCarrierModerator
from ..models import PermissionLink
from ..serializers import PermissionLinkSerializer, PermissionLinkCreateSerializer

LOG = logging.getLogger('transmission')


class PermissionLinkViewSet(mixins.CreateModelMixin,
                            mixins.DestroyModelMixin,
                            mixins.ListModelMixin,
                            viewsets.GenericViewSet):

    queryset = PermissionLink.objects.all()
    permission_classes = (
        (permissions.IsAuthenticated,
         ShipmentExists,
         IsOwnerShipperCarrierModerator, ) if settings.PROFILES_ENABLED
        else (permissions.AllowAny, ShipmentExists, )
    )
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
