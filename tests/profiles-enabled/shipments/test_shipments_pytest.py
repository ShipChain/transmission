import json

import pytest
from django.conf import settings
from django.urls import reverse
from moto import mock_sns
from shipchain_common.test_utils import AssertionHelper


class TestShipmentAftershipQuickadd:
    create_url = reverse('shipment-list', kwargs={'version': 'v1'})

    @pytest.fixture(autouse=True)
    def set_up(self, profiles_ids, mocked_engine_rpc):
        self.profiles_ids = profiles_ids
        self.base_create_attributes = {
            'storage_credentials_id': profiles_ids['storage_credentials_id'],
            'shipper_wallet_id': profiles_ids['shipper_wallet_id'],
            'carrier_wallet_id': profiles_ids['carrier_wallet_id'],
            'aftership_tracking': 'aftership_tracking'
        }

    @pytest.fixture
    def mock_aftership_validation_succeess(self, mock_successful_wallet_owner_calls):
        mock_successful_wallet_owner_calls.register_uri(mock_successful_wallet_owner_calls.POST,
                                                        f'{settings.AFTERSHIP_URL}couriers/detect',
                                                        )
        return mock_successful_wallet_owner_calls

    @pytest.fixture
    def mock_aftership_validation_failure(self, mock_successful_wallet_owner_calls):
        mock_successful_wallet_owner_calls.register_uri(mock_successful_wallet_owner_calls.POST,
                                                        f'{settings.AFTERSHIP_URL}couriers/detect',
                                                        status=400
                                                        )
        return mock_successful_wallet_owner_calls

    @pytest.fixture
    def mock_aftership_create_success(self, mock_aftership_validation_succeess):
        mock_aftership_validation_succeess.register_uri(mock_aftership_validation_succeess.POST,
                                                        f'{settings.AFTERSHIP_URL}trackings',
                                                        body=json.dumps({'data': {'tracking': {'id': 'id'}}}),)
        return mock_aftership_validation_succeess

    @pytest.fixture
    def mock_aftership_create_fail(self, mock_aftership_validation_succeess):
        mock_aftership_validation_succeess.register_uri(mock_aftership_validation_succeess.POST,
                                                        f'{settings.AFTERSHIP_URL}trackings',
                                                        status=400)
        return mock_aftership_validation_succeess

    @pytest.fixture(autouse=True)
    def mock_sns(self):
        mock_sns().start()
        import boto3
        settings.BOTO3_SESSION = boto3.Session(region_name='us-east-1')
        settings.SNS_CLIENT = settings.BOTO3_SESSION.client('sns')
        settings.SNS_CLIENT.create_topic(Name='transmission-events-test')

    @pytest.fixture
    def assertions_aftership_validation(self, assertions_shipment_create_profile_ids):
        assertions_shipment_create_profile_ids.append({
                'host': settings.AFTERSHIP_URL.replace('/v4/', ''),
                'path': '/v4/couriers/detect',
                'body': {'tracking': {'tracking_number': self.base_create_attributes['aftership_tracking']}}
            })
        return assertions_shipment_create_profile_ids

    @pytest.fixture
    def assertions_create_tracking(self, assertions_aftership_validation):
        assertions_aftership_validation.append({
                'host': settings.AFTERSHIP_URL.replace('/v4/', ''),
                'path': '/v4/trackings',
                'body': {'tracking': {'tracking_number': self.base_create_attributes['aftership_tracking']}}
            })
        return assertions_aftership_validation

    def test_successful_quickadd(self, client_alice, mock_aftership_create_success, assertions_create_tracking):
        response = client_alice.post(self.create_url, self.base_create_attributes)
        AssertionHelper.HTTP_202(response,
                                 entity_refs=AssertionHelper.EntityRef(
                                     resource='Shipment',
                                     attributes=self.base_create_attributes
                                 ))
        mock_aftership_create_success.assert_calls(assertions_create_tracking)

    def test_quickadd_create_fail(self, client_alice, mock_aftership_create_fail, assertions_create_tracking):
        response = client_alice.post(self.create_url, self.base_create_attributes)
        AssertionHelper.HTTP_400(response, error='Supplied tracking number has already been imported into Aftership')
        mock_aftership_create_fail.assert_calls(assertions_create_tracking)

    def test_quickadd_validation_fail(self, client_alice, mock_aftership_validation_failure,
                                      assertions_aftership_validation):
        response = client_alice.post(self.create_url, self.base_create_attributes)
        AssertionHelper.HTTP_400(response, error='Invalid aftership_tracking value')
        mock_aftership_validation_failure.assert_calls(assertions_aftership_validation)
