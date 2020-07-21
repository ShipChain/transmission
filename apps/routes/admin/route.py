"""
Copyright 2020 ShipChain, Inc.

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

from django.contrib import admin
from django.contrib.admin.forms import forms
from rest_framework import serializers

from apps.admin import object_detail_admin_link
from apps.routes.models import RouteLeg, Route
from apps.shipments.models import TransitState, Device, Shipment


class RouteForm(forms.ModelForm):
    driver_id = forms.UUIDField(required=False)
    device = forms.ModelChoiceField(queryset=Device.objects.all(), required=False)

    class Meta:
        model = Route
        fields = '__all__'

    def clean_device(self):
        device = self.cleaned_data.get('device')
        if "device" in self.changed_data:
            if not device:
                if not self.instance.device:
                    return None
                if not self.instance.can_disassociate_device():
                    self.add_error('device', 'Cannot remove device from Route in progress')
                return None

            try:
                device.prepare_for_reassignment()
            except serializers.ValidationError as exc:
                self.add_error('device', exc.detail)
        return device


class RouteLegInlineTab(admin.TabularInline):
    model = RouteLeg
    show_change_link = True
    can_delete = False
    verbose_name = 'Shipment for this route'
    verbose_name_plural = 'Shipments on this route'
    extra = 0
    readonly_fields = (
        'id',
        '_order',
        'shipment_link',
        'status_display',
    )

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        """Drop-down selection of only Shipments not associated to a Route"""
        try:
            if db_field.name == 'shipment':
                kwargs['queryset'] = Shipment.objects.filter(routeleg__isnull=True)
        except KeyError:
            pass
        return super(RouteLegInlineTab, self).formfield_for_foreignkey(db_field, request, **kwargs)

    def has_change_permission(self, request, obj=None):
        return False

    def shipment_link(self, obj):
        return object_detail_admin_link(obj.shipment)

    def status_display(self, obj):
        return TransitState(obj.shipment.state).label.upper()

    status_display.short_description = 'Status'


class RouteAdmin(admin.ModelAdmin):
    form = RouteForm

    list_display = (
        'id',
        'name',
        'driver_id',
        'owner_id',
        'device_id',
        'leg_count',
    )

    readonly_fields = (
        'id',
        'owner_id',
        'leg_count',
    )

    search_fields = [
        'id',
        'name',
    ]

    inlines = [
        RouteLegInlineTab,
    ]

    def leg_count(self, obj):
        return obj.routeleg_set.count()
    leg_count.short_description = 'Shipment Count'

    def has_add_permission(self, request):
        return False
