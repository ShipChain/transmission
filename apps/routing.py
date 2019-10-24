"""
Copyright 2018 ShipChain, Inc.

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

from channels.routing import ProtocolTypeRouter, URLRouter
from django.conf.urls import url

from . import consumers


# pylint:disable=invalid-name
websocket_urlpatterns = [
    url(r'^ws/(?P<user_id>[^/]+)/notifications$', consumers.AppsConsumer),
]

application = ProtocolTypeRouter({
    # (http->django views is added by default)
    'websocket': URLRouter(
        websocket_urlpatterns,
    ),
})
