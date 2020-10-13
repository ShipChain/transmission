#  Copyright 2020 ShipChain, Inc.
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
import json
import pytest
from moto import mock_sns, mock_sqs

from apps.sns import SNSClient


@pytest.fixture
def boto_session(boto, settings):
    settings.BOTO3_SESSION = boto.Session(region_name='us-east-1')
    return settings.BOTO3_SESSION


@pytest.fixture
def mocked_sns(boto_session, settings):
    with mock_sns():
        settings.SNS_CLIENT = boto_session.client('sns')
        settings.SNS_CLIENT.create_topic(Name=settings.SNS_ARN.rsplit(':', 1)[1])
        yield settings.SNS_CLIENT


@pytest.fixture
def sqs_queue(boto_session, mocked_sns, settings):
    with mock_sqs():
        sqs = boto_session.resource('sqs')
        queue = sqs.create_queue(QueueName='dummy-queue')

        mocked_sns.subscribe(
            TopicArn=settings.SNS_ARN,
            Protocol='sqs',
            Endpoint=queue.attributes['QueueArn']
        )
        yield queue


@pytest.fixture
def mocked_aftership_api(modified_http_pretty, settings):
    modified_http_pretty.register_uri(modified_http_pretty.POST, f'{settings.AFTERSHIP_URL}couriers/detect')
    modified_http_pretty.register_uri(modified_http_pretty.POST, f'{settings.AFTERSHIP_URL}trackings',
                                      body=json.dumps({'data': {'tracking': {'id': 'id-from-aftership', 'slug': 'aftership-slug'}}}),)


class TestSNS:
    def test_sns_notifications(self, mocked_sns, sqs_queue, shipment, mocked_aftership_api, modified_http_pretty, settings):
        # Initial Shipment creation should publish a SHIPMENT_UPDATE message
        messages = sqs_queue.receive_messages(MaxNumberOfMessages=1)
        assert len(messages) == 1
        sqs_message = json.loads(messages[0].body)
        assert sqs_message['MessageAttributes']['Type']['Value'] == SNSClient.MessageType.SHIPMENT_UPDATE
        assert json.loads(sqs_message['Message'])['id'] == shipment.id
        messages = sqs_queue.receive_messages(MaxNumberOfMessages=1)
        assert len(messages) == 0  # Queue should be clear

        # Addition of aftership tracking # should add SHIPMENT_UPDATE and AFTERSHIP_UPDATE messages
        shipment.quickadd_tracking = 'abc123'
        shipment.save()

        modified_http_pretty.assert_calls([{
                'host': settings.AFTERSHIP_URL.replace('/v4/', ''),
                'path': '/v4/trackings',
                'body': {'tracking': {'tracking_number': shipment.quickadd_tracking}}
        }])
        messages = sqs_queue.receive_messages(MaxNumberOfMessages=2)
        assert len(messages) == 2

        message_map = list(map(lambda msg: json.loads(msg.body), messages))
        shipment_message = list(filter(lambda msg: msg['MessageAttributes']['Type']['Value'] == SNSClient.MessageType.SHIPMENT_UPDATE, message_map))
        aftership_message = list(filter(lambda msg: msg['MessageAttributes']['Type']['Value'] == SNSClient.MessageType.AFTERSHIP_UPDATE, message_map))
        assert len(shipment_message) == 1
        assert len(aftership_message) == 1

        assert json.loads(shipment_message[0]['Message'])['id'] == shipment.id
        assert json.loads(aftership_message[0]['Message'])['shipmentId'] == shipment.id
        assert json.loads(aftership_message[0]['Message'])['aftershipTrackingId'] == 'id-from-aftership'
        assert json.loads(aftership_message[0]['Message'])['ownerId'] == shipment.updated_by

        messages = sqs_queue.receive_messages(MaxNumberOfMessages=1)
        assert len(messages) == 0  # Queue should be clear




