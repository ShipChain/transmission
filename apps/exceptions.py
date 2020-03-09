from rest_framework import status
from rest_framework.exceptions import APIException


class UrlShortenerError(APIException):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_detail = 'Internal Service Error.'
    default_code = 'server_error'

    def __init__(self, detail, status_code=None, code=None):
        super(UrlShortenerError, self).__init__(detail, code)
        self.detail = detail

        if status_code:
            self.status_code = status_code
