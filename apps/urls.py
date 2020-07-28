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
from apps.routes import views as routes
from apps.shipments import views as shipments

API_PREFIX = r'^api/(?P<version>(v1|v2))'

admin.site.site_header = 'Transmission Administration'

# pylint: disable=invalid-name
router = OptionalSlashRouter()

router.register(f'{API_PREFIX[1:]}/shipments', shipments.ShipmentViewSet)
router.register(f'{API_PREFIX[1:]}/jobs', jobs.JobsViewSet, basename='job')
router.register(f'{API_PREFIX[1:]}/events', eth.EventViewSet, basename='event')
router.register(f'{API_PREFIX[1:]}/transactions', eth.TransactionViewSet, basename='transaction')
router.register(f'{API_PREFIX[1:]}/devices', shipments.DeviceViewSet, basename='device')
router.register(f'{API_PREFIX[1:]}/imports/shipments', imports_app.ShipmentImportsViewSet, basename='import-shipments')
router.register(f'{API_PREFIX[1:]}/routes', routes.RouteViewSet, basename='route')

# Shipment's nested routes definition
nested_shipment = OptionalSlashNested(router, f'{API_PREFIX[1:]}/shipments', lookup='shipment')
nested_shipment.register(r'documents', documents.DocumentViewSet, basename='shipment-documents')
nested_shipment.register(r'transactions', eth.TransactionViewSet, basename='shipment-transactions')
nested_shipment.register(r'permission_links', shipments.PermissionLinkViewSet, basename='shipment-permissions')
nested_shipment.register(r'history', shipments.ShipmentHistoryListView, basename='shipment-history')
nested_shipment.register(r'notes', shipments.ShipmentNoteViewSet, basename='shipment-notes')
nested_shipment.register(r'tags', shipments.ShipmentTagViewSet, basename='shipment-tags')
nested_shipment.register(r'telemetry', shipments.TelemetryViewSet, basename='shipment-telemetry')

# Route's nested routes definition
nested_route = OptionalSlashNested(router, f'{API_PREFIX[1:]}/routes', lookup='route')
nested_route.register(r'legs', routes.RouteLegViewSet, basename='route-legs')

urlpatterns = [
    re_path('health/?$', management.health_check, name='health'),
    re_path(r'(^(api/v1/schema)|^$)', TemplateView.as_view(template_name='apidoc.html'), name='api_schema'),
    re_path(r'^admin/', admin.site.urls),
    re_path(f'{API_PREFIX[1:]}/documents/events/?$', documents.S3Events.as_view(), name='document-events'),
    re_path(f'{API_PREFIX[1:]}/shipments/overview/?$', shipments.ShipmentOverviewListView.as_view(),
            name='shipment-overview'),
    re_path(f'{API_PREFIX[1:]}/shipments/(?P<shipment_pk>[0-9a-f-]+)/actions/?$',
            shipments.ShipmentActionsView.as_view(), name='shipment-actions'),
    re_path(f'{API_PREFIX[1:]}/devices/(?P<device_pk>[0-9a-f-]+)/sensors/?$',
            shipments.SensorViewset.as_view(), name='device-sensors'),
]
urlpatterns += router.urls

urlpatterns += nested_shipment.urls
urlpatterns += nested_route.urls

urlpatterns = format_suffix_patterns(urlpatterns)

# Fallback to Generic API responses instead of Django's built-in rendered HTML responses
handler500 = 'shipchain_common.exceptions.server_error'
handler400 = 'shipchain_common.exceptions.bad_request'
handler404 = 'shipchain_common.exceptions.invalid_url'
