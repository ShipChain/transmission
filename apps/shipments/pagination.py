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

from collections import OrderedDict

from rest_framework.response import Response
from rest_framework_json_api.pagination import PageNumberPagination


class ShipmentHistoryPagination(PageNumberPagination):

    def get_paginated_response(self, data):
        next_page = None
        previous = None

        if self.page.has_next():
            next_page = self.page.next_page_number()
        if self.page.has_previous():
            previous = self.page.previous_page_number()

        response_data = OrderedDict([
            ('links', OrderedDict([
                ('first', self.build_link(1)),
                ('last', self.build_link(self.page.paginator.num_pages)),
                ('next', self.build_link(next_page)),
                ('prev', self.build_link(previous))
            ])),
            ('data', data),
            ('meta', {
                'pagination': OrderedDict([
                    ('page', self.page.number),
                    ('pages', self.page.paginator.num_pages),
                    ('count', self.page.paginator.count),
                ])
            })
        ])

        return Response(response_data)
