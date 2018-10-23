from django.test import TestCase

from apps.utils import assertDeepAlmostEqual


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
