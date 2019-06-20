#  Copyright 2019 ShipChain, Inc.
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.

from django.db import DEFAULT_DB_ALIAS, connections
from django.db.migrations.executor import MigrationExecutor
from django.http.response import HttpResponse
from rest_framework import permissions
from rest_framework.decorators import api_view, permission_classes, authentication_classes


@api_view(['GET'])
@authentication_classes(())
@permission_classes((permissions.AllowAny,))
def health_check(request):
    """
    This endpoint (/health) returns 200 if no migrations are pending, else 503
    https://engineering.instawork.com/elegant-database-migrations-on-ecs-74f3487da99f
    """
    executor = MigrationExecutor(connections[DEFAULT_DB_ALIAS])
    plan = executor.migration_plan(executor.loader.graph.leaf_nodes())
    return HttpResponse(status=503 if plan else 200)
