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

from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.utils.deprecation import MiddlewareMixin

CURRENT_THREAD = threading.current_thread()


class UserOrganizationMiddleware(MiddlewareMixin):

    def process_request(self, request):
        # We put this import here to avoid import error on start up
        from apps.authentication import PASSIVE_JWT_AUTHENTICATION, passive_credentials_auth

        user_id, org_id = None, None
        req_auth = request.headers._store.get('authorization')  # pylint: disable=protected-access
        username = request.POST.get('username')

        if req_auth:
            raw_token = req_auth[-1].split(' ')[-1]

            if settings.ENVIRONMENT.lower() in ('int', 'local'):
                from rest_framework_simplejwt.tokens import UntypedToken
                # We use UntypedToken with verify False here to avoid
                # unhandled exception to be thrown to the client
                token_user = PASSIVE_JWT_AUTHENTICATION.get_user(UntypedToken(raw_token, verify=False))
            else:
                token_user = passive_credentials_auth(req_auth[-1].split(' ')[-1])

            org_id = token_user.token.payload.get('organization_id')
            user_id = token_user.id

        elif username:
            user = None
            try:
                from apps.profiles.models import User
                user = User.objects.get(username=username)
            except (ImportError, ObjectDoesNotExist):
                pass

            if user is not None:
                user_id = user.id
                organization = user.organizations.first()
                org_id = organization.id if organization else None

        setattr(CURRENT_THREAD, 'organization_id', org_id)
        setattr(CURRENT_THREAD, 'user_id', user_id)
