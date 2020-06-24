from django.conf import settings
from rest_framework import permissions

from apps.permissions import get_user


class NestedRoutePermission(permissions.BasePermission):
    def has_permission(self, request, view):
        """
        If the user is not the owner of the Route (or not in the owning org), or if the Route does not exist,
        then views using this permission will return a 404.
        """
        from apps.routes.models import Route  # Avoid circular import

        if settings.PROFILES_ENABLED:
            user_id, organization_id = get_user(request)
            Route.objects.get(pk=view.kwargs['route_pk'],
                              owner_id__in=[organization_id, user_id] if organization_id else [user_id])
        else:
            Route.objects.get(pk=view.kwargs['route_pk'])
        return True
