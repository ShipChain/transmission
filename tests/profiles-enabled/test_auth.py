from django.http.request import HttpRequest
from django.test import TestCase
from rest_framework import exceptions

from apps.authentication import EngineRequest, passive_credentials_auth
from tests.utils import get_jwt

USERNAME = 'fake@shipchain.io'


class AuthTests(TestCase):

    def test_passive_jwt_auth(self):
        self.assertRaises(exceptions.AuthenticationFailed, passive_credentials_auth, "")
        user = passive_credentials_auth(get_jwt(username=USERNAME))
        self.assertEqual(user.is_authenticated, True)
        self.assertEqual(user.is_staff, False)
        self.assertEqual(user.is_superuser, False)
        self.assertEqual(user.username, USERNAME)

    def test_engine_auth_requires_header(self):
        engine_request = EngineRequest()
        request = HttpRequest()

        self.assertFalse(engine_request.has_permission(request, {}))
        request.META['X_NGINX_SOURCE'] = 'alb'
        self.assertFalse(engine_request.has_permission(request, {}))
        request.META['X_NGINX_SOURCE'] = 'internal'
        self.assertRaises(KeyError, engine_request.has_permission, request, {})
        request.META['X_SSL_CLIENT_VERIFY'] = 'NONE'
        self.assertFalse(engine_request.has_permission(request, {}))
        request.META['X_SSL_CLIENT_VERIFY'] = 'SUCCESS'
        self.assertRaises(KeyError, engine_request.has_permission, request, {})
        request.META['X_SSL_CLIENT_DN'] = '/CN=engine.h4ck3d'
        self.assertFalse(engine_request.has_permission(request, {}))
        request.META['X_SSL_CLIENT_DN'] = '/CN=profiles.test-internal'
        self.assertFalse(engine_request.has_permission(request, {}))
        request.META['X_SSL_CLIENT_DN'] = '/CN=engine.test-internal'
        self.assertTrue(engine_request.has_permission(request, {}))
