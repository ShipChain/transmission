from rest_framework import exceptions
from django.test import TestCase

from apps.authentication import PassiveJSONWebTokenAuthentication


class AuthTests(TestCase):

    def test_passive_jwt_auth(self):
        auth = PassiveJSONWebTokenAuthentication()
        self.assertRaises(exceptions.AuthenticationFailed, auth.authenticate_credentials, {})
        user = auth.authenticate_credentials({'sub': '000-000-0000', 'username': 'wat@wat.com', 'email': 'wat@wat.com'})
        self.assertEqual(user.is_authenticated(), True)
        self.assertEqual(user.is_staff(), False)
        self.assertEqual(user.is_superuser(), False)
        self.assertEqual(user.username, 'wat@wat.com')
