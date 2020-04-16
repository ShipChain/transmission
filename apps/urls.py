"""transmission URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/2.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from django.urls import re_path
from django.contrib import admin
from django.views.generic import TemplateView
from rest_framework.urlpatterns import format_suffix_patterns
from shipchain_common.routers import OptionalSlashRouter, OptionalSlashNested

from apps.documents import views as documents
from apps.eth import views as eth
from apps.imports import views as imports_app
from apps.jobs import views as jobs
from apps.management import views as management
from apps.shipments import views as shipments

API_PREFIX = r'^api/(?P<version>(v1|v2))'

admin.site.site_header = 'Transmission Administration'

# pylint: disable=invalid-name
router = OptionalSlashRouter()

router.register(f'{API_PREFIX[1:]}/shipments', shipments.ShipmentViewSet)
router.register(f'{API_PREFIX[1:]}/jobs', jobs.JobsViewSet, base_name='job')
router.register(f'{API_PREFIX[1:]}/events', eth.EventViewSet, base_name='event')
router.register(f'{API_PREFIX[1:]}/transactions', eth.TransactionViewSet, base_name='transaction')
router.register(f'{API_PREFIX[1:]}/devices', shipments.DeviceViewSet, base_name='device')
router.register(f'{API_PREFIX[1:]}/imports/shipments', imports_app.ShipmentImportsViewSet, base_name='import-shipments')

# Shipment's nested routes definition
nested_shipment = OptionalSlashNested(router, f'{API_PREFIX[1:]}/shipments', lookup='shipment')
nested_shipment.register(r'documents', documents.DocumentViewSet, base_name='shipment-documents')
nested_shipment.register(r'transactions', eth.TransactionViewSet, base_name='shipment-transactions')
nested_shipment.register(r'permission_links', shipments.PermissionLinkViewSet, base_name='shipment-permissions')
nested_shipment.register(r'history', shipments.ShipmentHistoryListView, base_name='shipment-history')
nested_shipment.register(r'notes', shipments.ShipmentNoteViewSet, base_name='shipment-notes')
nested_shipment.register(r'tags', shipments.ShipmentTagViewSet, base_name='shipment-tags')
nested_shipment.register(r'telemetry', shipments.TelemetryViewSet, base_name='shipment-telemetry')

# Device's nested routes definition
nested_devices = OptionalSlashNested(router, f'{API_PREFIX[1:]}/devices', lookup='device')
nested_devices.register(r'sensors', shipments.SensorViewset, base_name='device-sensor')

urlpatterns = [
    re_path('health/?$', management.health_check, name='health'),
    re_path(r'(^(api/v1/schema)|^$)', TemplateView.as_view(template_name='apidoc.html'), name='api_schema'),
    re_path(r'^admin/', admin.site.urls),
    re_path(f'{API_PREFIX[1:]}/documents/events/?$', documents.S3Events.as_view(), name='document-events'),
    re_path(f'{API_PREFIX[1:]}/shipments/overview/?$', shipments.ShipmentOverviewListView.as_view(),
            name='shipment-overview'),
    re_path(f'{API_PREFIX[1:]}/shipments/(?P<shipment_pk>[0-9a-f-]+)/actions/?$',
            shipments.ShipmentActionsView.as_view(), name='shipment-actions'),
]
urlpatterns += router.urls

urlpatterns += nested_shipment.urls
urlpatterns += nested_devices.urls

urlpatterns = format_suffix_patterns(urlpatterns)

# Fallback to Generic API responses instead of Django's built-in rendered HTML responses
handler500 = 'shipchain_common.exceptions.server_error'
handler400 = 'shipchain_common.exceptions.bad_request'
handler404 = 'shipchain_common.exceptions.invalid_url'
