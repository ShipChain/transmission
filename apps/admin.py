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
