import logging
import re

from django.conf import settings
from django.core.exceptions import FieldError, FieldDoesNotExist, ValidationError, ObjectDoesNotExist
from django.http import JsonResponse
from rest_framework import status
from rest_framework.response import Response
from rest_framework_json_api import utils
from rest_framework_json_api.exceptions import rendered_with_json_api

LOG = logging.getLogger('transmission')


def unhandled_drf_exception_handler(exc, context):
    """
    Deal with exceptions that DRF doesn't catch and return a JSON:API errors object.
    For model query parameters, attempt to identify the parameter that caused the exception:
    "Cannot resolve keyword 'xname' into field. Choices are: name, title, ...."
    Unfortunately there's no "clean" way to identify which field caused the exception other than
    parsing the error message. If the parse fails, a more generic error is reported.
    Even a 500 error for a jsonapi view should return a jsonapi error object, not an HTML response.
    """
    is_uniform = getattr(settings, 'JSON_API_UNIFORM_EXCEPTIONS', False)
    if not rendered_with_json_api(context['view']) and not is_uniform:
        return None

    errors = []

    if isinstance(exc, (FieldDoesNotExist,)):
        keymatch = re.compile(r"^Cannot resolve keyword '(?P<keyword>[\w_]+)' into field.")
        matched = keymatch.match(str(exc))
        bad_kw = matched.group("keyword") if matched else "?"

        status_code = 400
        errors.append({
            "detail": f"Missing Query Parameter: '{bad_kw}'",
            "source": {
                "parameter": bad_kw,
            },
            "status": str(status_code),
        })
    elif isinstance(exc, (FieldError,)):
        keymatch = re.compile(r"^Invalid field name\(s\) for model (?P<model>[\w_]+): '(?P<keyword>[\w_]+)'.")
        matched = keymatch.match(str(exc))

        bad_kw = matched.group("keyword") if matched else "?"
        bad_model = matched.group("model") if matched else "?"

        status_code = 400
        errors.append({
            "detail": f"No field {bad_kw} on model {bad_model}",
            "source": {
                "parameter": bad_kw,
            },
            "status": str(status_code),
        })
    elif isinstance(exc, (ValidationError,)):
        status_code = 400
        for error_key in exc.error_dict.keys():
            errors.append({
                "detail": exc.error_dict[error_key][0].message,
                "source": {
                    "pointer": f"data/attributes/{error_key}",
                },
                "status": str(status_code),
            })
    elif isinstance(exc, (ObjectDoesNotExist,)):
        status_code = 404
        errors.append({
            "detail": exc.args[0],
            "source": {
                "pointer": "/data",
            },
            "status": str(status_code),
        })
    else:
        LOG.error(f'HTTP 500 error: {exc}')
        status_code = 500
        errors.append({
            "code": "server_error",
            "detail": str(exc),
            "status": str(status_code),
            "title": "Internal Server Error",
        })

    response = Response(errors, status=status_code)

    is_json_api_view = rendered_with_json_api(context['view'])
    if not is_json_api_view:
        response.data = utils.format_errors(response.data)

    return response


def exception_handler(exc, context):
    # Import this here to avoid potential edge-case circular imports, which
    # crashes with:
    # "ImportError: Could not import 'rest_framework_json_api.parsers.JSONParser' for API setting
    # 'DEFAULT_PARSER_CLASSES'. ImportError: cannot import name 'exceptions'.'"
    #
    # Also see: https://github.com/django-json-api/django-rest-framework-json-api/issues/158
    from rest_framework.views import exception_handler as drf_exception_handler

    # Render exception with DRF
    response = drf_exception_handler(exc, context)
    if not response:
        return unhandled_drf_exception_handler(exc, context)

    if response.status_code == status.HTTP_400_BAD_REQUEST:
        for field, detail in list(exc.detail.items()):
            if isinstance(detail, dict):
                for key in detail.keys():
                    exc.detail[f'{field}.{key}'] = detail[key]
                exc.detail.pop(field)

    # Use regular DRF format if not rendered by DRF JSON API and not uniform
    is_json_api_view = rendered_with_json_api(context['view'])
    is_uniform = getattr(settings, 'JSON_API_UNIFORM_EXCEPTIONS', False)
    if not is_json_api_view and not is_uniform:
        return response

    # Convert to DRF JSON API error format
    response = utils.format_drf_errors(response, context, exc)

    # Add top-level 'errors' object when not rendered by DRF JSON API
    if not is_json_api_view:
        response.data = utils.format_errors(response.data)

    return response


def server_error(request, *args, **kwargs):
    """
    Generic 500 error handler.
    """
    data = {
        "errors": [{
            "detail": "Internal Server Error",
            "status": "500"
        }]
    }
    return JsonResponse(data, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


def bad_request(request, exception, *args, **kwargs):
    """
    Generic 400 error handler.
    """
    data = {
        "errors": [{
            "detail": "Bad Request",
            "status": "400"
        }]
    }
    return JsonResponse(data, status=status.HTTP_400_BAD_REQUEST)
