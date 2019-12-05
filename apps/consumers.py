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

from string import Template
from channels.db import database_sync_to_async
from enumfields import Enum
from rest_framework.renderers import JSONRenderer

from apps.authentication import AsyncJsonAuthConsumer

from apps.jobs.models import AsyncJob
from apps.shipments.models import TrackingData

from apps.jobs.serializers import AsyncJobSerializer
from apps.shipments.geojson import render_point_feature


class EventTypes(Enum):
    error = 0
    asyncjob_update = 1
    trackingdata_update = 2


class AppsConsumer(AsyncJsonAuthConsumer):
    async def jobs_update(self, event):
        job_json = await database_sync_to_async(self.render_async_job)(event['async_job_id'])
        await self.send(job_json)

    def render_async_job(self, job_id):
        job = AsyncJob.objects.get(id=job_id)
        return JSONRenderer().render({'event': EventTypes.asyncjob_update.name,
                                      'data': AsyncJobSerializer(job).data}).decode()

    async def tracking_data_save(self, event):
        tracking_data_json = await database_sync_to_async(self.render_async_tracking_data)(event['tracking_data_id'])
        await self.send(tracking_data_json)

    def render_async_tracking_data(self, data_id):
        data = TrackingData.objects.filter(id=data_id)
        return Template('{"event": "$event", "data": $geojson}').substitute(
            event=EventTypes.trackingdata_update.name,
            geojson=render_point_feature(data),
        )

    async def receive_json(self, content, **kwargs):
        await self.send_json({
            "event": EventTypes.error.name,
            "data": "This websocket endpoint is read-only",
        })
