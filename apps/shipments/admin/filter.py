from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from apps.shipments.models import TransitState


class StateFilter(admin.FieldListFilter):
    parameter_name = 'state'

    def __init__(self, field, request, params, *args, **kwargs):
        super().__init__(field, request, params, *args, **kwargs)
        self.lookup_choices = self.lookups(request, args[1])

        if self.parameter_name in params:
            self.used_parameters[self.parameter_name] = params.pop(self.parameter_name)

    def value(self):
        return self.used_parameters.get(self.parameter_name)

    def lookups(self, request, model_admin):
        return TransitState.choices()

    def expected_parameters(self):
        return [self.parameter_name]

    def choices(self, changelist):
        yield {
            'selected': self.value() is None,
            'query_string': changelist.get_query_string(remove=[self.parameter_name]),
            'display': _('All'),
        }
        for lookup, title in self.lookup_choices:
            yield {
                'selected': self.value() == str(lookup),
                'query_string': changelist.get_query_string({self.parameter_name: lookup}),
                'display': title,
            }
