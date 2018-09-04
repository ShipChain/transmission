from rest_framework import exceptions
from django.test import TestCase

from apps.utils import assertDeepAlmostEqual, PassiveJSONWebTokenAuthentication


class UtilsTests(TestCase):
    def test_assert_almost_equal(self):
        assertDeepAlmostEqual(self,
                              expected={
                                  'data': {
                                      'testing': 123.4567890123456789
                                  }
                              },
                              actual={
                                  'data': {
                                      'testing': 123.4567890123456788
                                  }
                              })
        self.assertRaises(AssertionError, assertDeepAlmostEqual,
                          test_case=self,
                          expected={
                              'testing': 123
                          },
                          actual={
                              'testing': 124
                          })

    def test_passive_jwt_auth(self):
        auth = PassiveJSONWebTokenAuthentication()
        self.assertRaises(exceptions.AuthenticationFailed, auth.authenticate_credentials, {})
        user = auth.authenticate_credentials({'sub': '000-000-0000', 'username': 'wat@wat.com', 'email': 'wat@wat.com'})
        self.assertEqual(user.is_authenticated(), True)
        self.assertEqual(user.is_staff(), False)
        self.assertEqual(user.is_superuser(), False)
        self.assertEqual(user.username, 'wat@wat.com')
