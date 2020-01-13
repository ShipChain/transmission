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

import json

from pygments import highlight
from pygments.lexers import JsonLexer
from pygments.formatters import HtmlFormatter

from django.utils.html import format_html
from rest_framework.reverse import reverse


def admin_change_url(obj):
    if obj:
        app_label = obj._meta.app_label
        model_name = obj._meta.model.__name__.lower()
        return reverse('admin:{}_{}_change'.format(
            app_label, model_name
        ), args=(obj.pk,))

    return ''


def admin_link(attr, short_description, empty_description="-"):
    """Decorator used for rendering a link to a related model in
    the admin detail page.
    attr (str):
        Name of the related field.
    short_description (str):
        Name if the field.
    empty_description (str):
        Value to display if the related field is None.
    The wrapped method receives the related object and should
    return the link text.
    Usage:
        @admin_link('credit_card', _('Credit Card'))
        def credit_card_link(self, credit_card):
            return credit_card.name
    """

    def wrap(func):
        def field_func(self, obj):
            related_obj = getattr(obj, attr)
            if related_obj is None:
                return empty_description
            url = admin_change_url(related_obj)
            return format_html(
                '<a href="{}">{}</a>',
                url,
                func(self, related_obj)
            )

        field_func.short_description = short_description
        field_func.allow_tags = True
        return field_func

    return wrap


class SafeJson(str):
    def __html__(self):
        return self


def pretty_json_print(field, indent=2, sort_keys=True, line_separator=u'\n'):
    response = json.dumps(field, sort_keys=sort_keys, indent=indent)

    # Get the Pygments formatter
    formatter = HtmlFormatter(style='colorful', lineseparator=line_separator)

    # Highlight the data
    response = highlight(response, JsonLexer(), formatter)

    # Get the stylesheet
    style = "<style>" + formatter.get_style_defs() + "</style><br>"

    # Safe the output
    return SafeJson(style + response)


def object_detail_admin_link(obj):
    """
    Returns the url admin link of the object passed in argument
    """
    return format_html(
        '<a href="{}">{}</a>',
        admin_change_url(obj),
        obj.id if obj else ''
    )


class ShipmentAdminDisplayMixin:
    """
    This mixin aims at facilitating the addition of a shipment link on a list
    or detail page.

    example:
        class MyModelAdmin(ShipmentAdminDisplayMixin, ModelAdmin):
            ...

            list_display = (
                ...
                'shipment_display',
            )

            # Or for detail display
            readonly_fields = (
                ...
                'shipment_display',
            )
    """
    def shipment_display(self, obj):
        return object_detail_admin_link(obj.shipment)

    shipment_display.short_description = "Shipment"


class NoWritePermissionMixin:
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
