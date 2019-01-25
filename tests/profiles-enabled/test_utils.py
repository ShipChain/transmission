from django.test import TestCase

from apps.utils import assertDeepAlmostEqual, snake_to_sentence


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

    def test_snake_to_sentence(self):
        snake_case = "Lorem_ipsum_dolor_sit_amet,_consectetur_adipiscing_elit,"
        unsnaked = snake_to_sentence(snake_case)
        self.assertEqual(unsnaked, 'Lorem Ipsum Dolor Sit Amet, Consectetur Adipiscing Elit,')
