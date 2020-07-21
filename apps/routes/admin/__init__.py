from django.contrib import admin

from apps.routes.models import Route, RouteLeg

from .route import RouteAdmin
from .route_leg import RouteLegAdmin


admin.site.register(Route, RouteAdmin)
admin.site.register(RouteLeg, RouteLegAdmin)
