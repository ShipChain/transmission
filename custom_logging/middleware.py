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

import threading

from django.utils.deprecation import MiddlewareMixin

current_thread = threading.current_thread()


class OrganizationIdMiddleware(MiddlewareMixin):

    def process_request(self, request):
        from apps.authentication import passive_credentials_auth

        token_user = passive_credentials_auth(request.headers._store['authorization'][-1].split(' ')[-1])
        org_id = token_user.token.payload.get('organization_id')
        user_id = getattr(token_user, 'id')

        setattr(current_thread, 'organization_id', org_id if org_id else 'N.A')
        setattr(current_thread, 'user_id', user_id)
