import json
from django.conf import settings


class SNSClient:
    class MessageType:
        AFTERSHIP_UPDATE = 'AftershipTrackingUpdate'
        SHIPMENT_UPDATE = 'ShipmentUpdate'

    def _publish(self, message_type, **kwargs):
        settings.BOTO3_SESSION.client('sns').publish(
            TopicArn=settings.SNS_ARN,
            Message=json.dumps(kwargs),
            MessageAttributes={
                'Type': {
                    'DataType': 'String',
                    'StringValue': message_type
                }
            }
        )

    def aftership_tracking_update(self, shipment, aftership_id):
        self._publish(
            SNSClient.MessageType.AFTERSHIP_UPDATE,
            owner_id=shipment.owner_id,
            aftership_id=aftership_id,
            shipment_id=shipment.id
        )

    def shipment_update(self, shipment):
        self._publish(
            SNSClient.MessageType.SHIPMENT_UPDATE,
            id=shipment.id
        )
