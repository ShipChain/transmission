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
import json
from string import Template

from channels.db import database_sync_to_async
from enumfields import Enum
from rest_framework_json_api.renderers import JSONRenderer

from apps.authentication import AsyncJsonAuthConsumer
from apps.jobs.models import AsyncJob, JobState
from apps.jobs.serializers import AsyncJobSerializer
from apps.jobs.views import JobsViewSet
from apps.shipments.geojson import render_point_feature
from apps.shipments.models import Shipment, TrackingData, TelemetryData
from apps.shipments.serializers import ShipmentTxSerializer
from apps.shipments.views import ShipmentViewSet


class EventTypes(Enum):
    error = 0
    asyncjob_update = 1
    trackingdata_update = 2
    shipment_update = 3


class AppsConsumer(AsyncJsonAuthConsumer):
    async def jobs_update(self, event):
        job_json = await database_sync_to_async(self.render_async_job)(event['async_job_id'])
        await self.send(job_json)

    def render_async_job(self, job_id):
        job = AsyncJob.objects.get(id=job_id)
        response = AsyncJobSerializer(job)

        asyncjob_json = JSONRenderer().render(response.data, renderer_context={'view': JobsViewSet()}).decode()
        return Template('{"event": "$event", "data": $asyncjob}').substitute(
            event=EventTypes.asyncjob_update.name,
            asyncjob=asyncjob_json
        )

    async def shipments_update(self, event):
        fields_json = await database_sync_to_async(self.render_shipment_fields)(event['shipment_id'])
        await self.send(fields_json)

    def render_shipment_fields(self, shipment_id):
        shipment = Shipment.objects.get(id=shipment_id)
        async_jobs = shipment.asyncjob_set.filter(state__in=[JobState.PENDING, JobState.RUNNING])
        response = ShipmentTxSerializer(shipment)
        response.instance.async_job_id = async_jobs.latest('created_at').id if async_jobs else None

        shipment_json = JSONRenderer().render(response.data, renderer_context={'view': ShipmentViewSet()}).decode()
        return Template('{"event": "$event", "data": $shipment}').substitute(
            event=EventTypes.shipment_update.name,
            shipment=shipment_json,
        )

    async def tracking_data_save(self, event):
        tracking_data_json = await database_sync_to_async(self.render_async_tracking_data)(event['tracking_data_id'])
        await self.send(tracking_data_json)

    def render_async_tracking_data(self, data_id):
        data = TrackingData.objects.filter(id=data_id)
        return Template('{"event": "$event", "data": {"shipment_id": "$shipment_id", "feature": $geojson}}').substitute(
            event=EventTypes.trackingdata_update.name,
            shipment_id=data.first().shipment_id,
            geojson=render_point_feature(data),
        )

    async def telemetry_data_save(self, event):
        telemetry_data_json = await database_sync_to_async(self.render_async_telemetry_data)(event['telemetry_data_id'])
        await self.send(telemetry_data_json)

    def render_async_telemetry_data(self, data_id):
        data = TelemetryData.objects.filter(id=data_id).first()
        telemetry_data = {
            'sensor_id': data.sensor_id,
            'hardware_id': data.hardware_id,
            'timestamp': str(data.timestamp.iso_format()),
            'value': data.value,
        }
        return Template(
            '{"event": "$event", "data": {"shipment_id": "$shipment_id", "feature": $telemetry}}').substitute(
            event=EventTypes.trackingdata_update.name,
            shipment_id=data.shipment_id,
            telemetry=json.dumps(telemetry_data),
        )

    async def receive_json(self, content, **kwargs):
        await self.send_json({
            "event": EventTypes.error.name,
            "data": "This websocket endpoint is read-only",
        })
