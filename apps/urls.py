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
from django.conf.urls import url
from django.views.generic import TemplateView
from rest_framework.urlpatterns import format_suffix_patterns
from rest_framework import routers
from apps.jobs import views as jobs
from apps.shipments import views as shipments
from apps.eth import views as eth


API_PREFIX = r'^api/(?P<version>(v1|v2))'

# pylint: disable=invalid-name

router = routers.SimpleRouter()
router.register(f'{API_PREFIX[1:]}/shipments', shipments.ShipmentViewSet)
router.register(f'{API_PREFIX[1:]}/locations', shipments.LocationViewSet)
router.register(f'{API_PREFIX[1:]}/jobs', jobs.JobsViewSet, base_name='job')
router.register(f'{API_PREFIX[1:]}/events', eth.EventViewSet, base_name='event')
router.register(f'{API_PREFIX[1:]}/transactions', eth.TransactionViewSet, base_name='transaction')
router.register(f'{API_PREFIX[1:]}/transactionreceipts', eth.TransactionReceiptViewSet, base_name='transactionreceipts')


urlpatterns = [
    url(
        r'(^(api/v1/schema)|^$)',
        TemplateView.as_view(template_name='apidoc.html'),
        name='api_schema'
    ),
]
urlpatterns += router.urls

urlpatterns = format_suffix_patterns(urlpatterns)

# Fallback to Generic API responses instead of Django's built-in rendered HTML responses
handler500 = 'apps.exceptions.server_error'
handler400 = 'apps.exceptions.bad_request'
handler404 = 'apps.exceptions.invalid_url'
