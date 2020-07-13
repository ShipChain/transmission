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

from django.contrib.gis.db.models import GeometryField
from django.contrib.gis.geos import Point
from django.core.validators import RegexValidator
from django.db import models
import geocoder
from geocoder.keys import mapbox_access_token
from influxdb_metrics.loader import log_metric
from rest_framework.exceptions import Throttled
from rest_framework.status import HTTP_503_SERVICE_UNAVAILABLE
from shipchain_common.utils import random_id

from apps.simple_history import TxmHistoricalRecords, AnonymousHistoricalMixin

LOG = logging.getLogger('transmission')

# pylint: disable=too-many-branches


class Location(AnonymousHistoricalMixin, models.Model):
    id = models.CharField(primary_key=True, default=random_id, max_length=36)

    phone_regex = RegexValidator(regex=r'^(\+\d{1,2}\s)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}',
                                 message="Invalid phone number.")
    country_regex = RegexValidator(regex=r'^A[^ABCHJKNPVY]|B[^CKPUX]|C[^BEJPQST]|D[EJKMOZ]|E[CEGHRST]|F[IJKMOR]|'
                                         r'G[^CJKOVXZ]|H[KMNRTU]|I[DEL-OQ-T]|J[EMOP]|K[EGHIMNPRWYZ]|L[ABCIKR-VY]|'
                                         r'M[^BIJ]|N[ACEFGILOPRUZ]|OM|P[AE-HK-NRSTWY]|QA|R[EOSUW]|S[^FPQUW]|'
                                         r'T[^ABEIPQSUXY]|U[AGMSYZ]|V[ACEGINU]|WF|WS|YE|YT|Z[AMW]',
                                         message="Invalid ISO 3166-1 alpha-2 country code.")
    name = models.CharField(max_length=255)
    address_1 = models.CharField(max_length=255, blank=True, null=True)
    address_2 = models.CharField(max_length=255, blank=True, null=True)
    city = models.CharField(max_length=255, blank=True, null=True)
    state = models.CharField(max_length=255, blank=True, null=True)
    country = models.CharField(max_length=2, validators=[country_regex], blank=True, null=True)
    postal_code = models.CharField(max_length=255, blank=True, null=True)

    phone_number = models.CharField(validators=[phone_regex], max_length=255, blank=True, null=True)
    fax_number = models.CharField(validators=[phone_regex], max_length=255, blank=True, null=True)

    # Contact fields
    contact_email = models.EmailField(blank=True, null=True)
    contact_name = models.CharField(max_length=255, blank=True, null=True)

    geometry = GeometryField(null=True)

    updated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    # Model's history tracking definition
    history = TxmHistoricalRecords()

    def get_lat_long_from_address(self):
        LOG.debug(f'Creating lat/long point for location {self.id}')
        log_metric('transmission.info', tags={'method': 'locations.get_lat_long', 'module': __name__})
        parsing_address = ''

        if self.address_1:
            parsing_address = self.address_1
        if self.address_2:
            parsing_address += ', ' + self.address_2
        if self.city:
            parsing_address += ', ' + self.city
        if self.state:
            parsing_address += ', ' + self.state
        if self.country:
            parsing_address += ', ' + self.country
        if self.postal_code:
            parsing_address += ', ' + self.postal_code

        if parsing_address:
            if mapbox_access_token:
                self.geocoder(parsing_address, 'mapbox')
            else:
                self.geocoder(parsing_address, 'google')

    def geocoder(self, parsing_address, method):
        if method == 'mapbox':
            geocoder_response = geocoder.mapbox(parsing_address)
        elif method == 'google':
            geocoder_response = geocoder.google(parsing_address)

        if not geocoder_response.ok:
            if 'OVER_QUERY_LIMIT' in geocoder_response.error:
                log_metric('transmission.errors', tags={'method': 'locations.geocoder',
                                                        'code': 'service_unavailable', 'module': __name__,
                                                        'detail': f'error calling {method} geocoder'})
                LOG.debug(f'{method} geocode for address {parsing_address} failed as query limit was reached')
                raise Throttled(detail=f'Over Query Limit for {method}', code=HTTP_503_SERVICE_UNAVAILABLE)

            if 'No results found' or 'ZERO_RESULTS' in geocoder_response.error:
                log_metric('transmission.errors', tags={'method': 'locations.geocoder',
                                                        'code': 'internal_server_error', 'module': __name__,
                                                        'detail': f'No results returned from {method} geocoder'})
                LOG.debug(f'{method} geocode for address {parsing_address} failed with zero results returned')
                LOG.warning(f'Cannot Geolocalize Address for location: {self.id}')

        else:
            self.geometry = Point(geocoder_response.xy)
