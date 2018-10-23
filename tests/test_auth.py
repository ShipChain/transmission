from rest_framework import exceptions
from django.test import TestCase
from django.http.request import HttpRequest

from apps.authentication import PassiveJSONWebTokenAuthentication, EngineRequest


class AuthTests(TestCase):

    def test_passive_jwt_auth(self):
        auth = PassiveJSONWebTokenAuthentication()
        self.assertRaises(exceptions.AuthenticationFailed, auth.authenticate_credentials, {})
        user = auth.authenticate_credentials({'sub': '000-000-0000', 'username': 'wat@wat.com', 'email': 'wat@wat.com'})
        self.assertEqual(user.is_authenticated(), True)
        self.assertEqual(user.is_staff(), False)
        self.assertEqual(user.is_superuser(), False)
        self.assertEqual(user.username, 'wat@wat.com')

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
