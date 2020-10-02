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
from datetime import datetime, timedelta
from unittest import mock

import pytest
from django.conf import settings
from django.urls import reverse
from jose import jws
from moto import mock_iot
from rest_framework import status
from shipchain_common.test_utils import AssertionHelper
from shipchain_common.utils import random_id

from apps.shipments.models import TrackingData


@pytest.fixture
def mocked_sensors_success(mock_successful_wallet_owner_calls, device):
    mock_successful_wallet_owner_calls.register_uri(
        mock_successful_wallet_owner_calls.GET,
        f'{settings.PROFILES_URL}/api/v1/device/{device.id}/sensor',
        body=json.dumps({"links": {
            "first": f"{settings.PROFILES_URL}/api/v1/device/",
            "last": f"{settings.PROFILES_URL}/api/v1/device/",
            "next": None,
        }, "data": [{}]}),
        status=status.HTTP_200_OK)
    return mock_successful_wallet_owner_calls


@pytest.fixture
def mocked_sensors_fail(mock_successful_wallet_owner_calls, device):
    mock_successful_wallet_owner_calls.register_uri(mock_successful_wallet_owner_calls.GET,
                                                    f'{settings.PROFILES_URL}/api/v1/device/{device.id}/sensor',
                                                    body=json.dumps({'errors': [{'detail': '404 error'}]}),
                                                    status=status.HTTP_404_NOT_FOUND)
    return mock_successful_wallet_owner_calls


@pytest.fixture
def mocked_sensors_non_json(mock_successful_wallet_owner_calls, device):
    mock_successful_wallet_owner_calls.register_uri(mock_successful_wallet_owner_calls.GET,
                                                    f'{settings.PROFILES_URL}/api/v1/device/{device.id}/sensor',
                                                    body=str(datetime.now()),
                                                    status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    return mock_successful_wallet_owner_calls


class TestSensorsWithShipmentList:
    @pytest.fixture(autouse=True)
    def set_up(self, device, shipment_alice_with_device):
        self.device = device
        self.shipment_alice_with_device = shipment_alice_with_device
        self.url = reverse('device-sensors', kwargs={'version': 'v1', 'device_pk': device.id})

    def test_unauthenticated_user_fails(self, api_client):
        response = api_client.get(self.url)
        AssertionHelper.HTTP_403(response, vnd=False, error='You do not have permission to perform this action.')

    def test_shipment_owner_succeeds(self, client_alice, mocked_sensors_success):
        response = client_alice.get(self.url)
        AssertionHelper.HTTP_200(response, is_list=True)
        mocked_sensors_success.assert_calls([{
                'path': f'/api/v1/device/{self.device.id}/sensor',
                'body': '',
                'host': settings.PROFILES_URL.replace('http://', ''),
            }])

    def test_wallet_owner_succeeds(self, client_bob, mocked_sensors_success,
                                   successful_wallet_owner_calls_assertions):
        response = client_bob.get(self.url)
        AssertionHelper.HTTP_200(response, is_list=True)
        successful_wallet_owner_calls_assertions.append({
                'path': f'/api/v1/device/{self.device.id}/sensor',
                'body': '',
                'host': settings.PROFILES_URL.replace('http://', ''),
            })
        mocked_sensors_success.assert_calls(successful_wallet_owner_calls_assertions)

    def test_non_wallet_owner_fails(self, client_bob, nonsuccessful_wallet_owner_calls_assertions,
                                    mock_non_wallet_owner_calls):
        response = client_bob.get(self.url)
        AssertionHelper.HTTP_403(response, vnd=False, error='You do not have permission to perform this action.')
        mock_non_wallet_owner_calls.assert_calls(nonsuccessful_wallet_owner_calls_assertions)

    def test_expired_permission_link_fails(self, api_client, permission_link_device_shipment_expired):
        response = api_client.get(f'{self.url}?permission_link={permission_link_device_shipment_expired.id}')
        AssertionHelper.HTTP_403(response, vnd=False, error='You do not have permission to perform this action.')

    def test_permission_link_succeeds(self, api_client, mocked_sensors_success, permission_link_device_shipment):
        response = api_client.get(f'{self.url}?permission_link={permission_link_device_shipment.id}')
        AssertionHelper.HTTP_200(response, is_list=True)
        mocked_sensors_success.assert_calls([{
                'path': f'/api/v1/device/{self.device.id}/sensor',
                'body': '',
                'host': settings.PROFILES_URL.replace('http://', ''),
            }])

    def test_fails_pass_through(self, client_alice, mocked_sensors_fail):
        response = client_alice.get(self.url)
        AssertionHelper.HTTP_404(response, error='404 error')
        mocked_sensors_fail.assert_calls([{
                'path': f'/api/v1/device/{self.device.id}/sensor',
                'body': '',
                'host': settings.PROFILES_URL.replace('http://', ''),
            }])

    def test_queries_pass_through(self, client_alice, mocked_sensors_success):
        response = client_alice.get(f'{self.url}?search=field')
        AssertionHelper.HTTP_200(response, is_list=True)
        mocked_sensors_success.assert_calls([{
                'path': f'/api/v1/device/{self.device.id}/sensor',
                'body': '',
                'host': settings.PROFILES_URL.replace('http://', ''),
                'query': {'search': 'field'}
            }])

    def test_non_json_fails(self, client_alice, mocked_sensors_non_json):
        response = client_alice.get(self.url)
        # AssertionHelper.HTTP_503(response, vnd=False, error='Invalid response returned from profiles.')
        assert response.status_code == 503
        assert response.json()['detail'] == 'Invalid response returned from profiles.'
        mocked_sensors_non_json.assert_calls([{
                'path': f'/api/v1/device/{self.device.id}/sensor',
                'body': '',
                'host': settings.PROFILES_URL.replace('http://', ''),
            }])


@mock_iot
class TestTrackingData:
    create_url = reverse('shipment-list', kwargs={'version': 'v1'})

    @pytest.fixture(autouse=True)
    def set_up(self, mocked_engine_rpc, mocked_iot_api, mock_requests_session, device, mocked_iot):
        self.mocked_iot = mocked_iot
        self.url_device = reverse('device-tracking', kwargs={'version': 'v1', 'pk': device.id})
        self.url_random = reverse('device-tracking', kwargs={'version': 'v1', 'pk': random_id()})
        self.device = device
        with open('tests/data/eckey.pem', 'r') as key_file:
            self.key_pem = key_file.read()
        with open('tests/data/eckey2.pem', 'r') as key_file:
            self.key_pem2 = key_file.read()

    def sign_tracking(self, track_dic, device, key=None, certificate_id=None, device_id=None):
        certificate_id = device.certificate_id if not certificate_id else certificate_id
        key = self.key_pem if not key else key
        track_dic['device_id'] = device_id if device_id else device.id
        return jws.sign(track_dic, key=key, headers={'kid': certificate_id}, algorithm='ES256')

    def test_only_post_calls(self, api_client, tracking_data):
        signed_tracking_data = self.sign_tracking(tracking_data, self.device)
        response = api_client.get(self.url_device)
        AssertionHelper.HTTP_405(response)

        response = api_client.put(self.url_device, data={'payload': signed_tracking_data})
        AssertionHelper.HTTP_405(response)

        response = api_client.patch(self.url_device, data={'payload': signed_tracking_data})
        AssertionHelper.HTTP_405(response)

        response = api_client.delete(self.url_device)
        AssertionHelper.HTTP_405(response)

    def test_requires_shipment_association(self, api_client, shipment_alice, tracking_data):
        signed_tracking_data = self.sign_tracking(tracking_data, self.device)

        response = api_client.post(self.url_device, {'payload': signed_tracking_data})
        AssertionHelper.HTTP_403(response, error='No shipment/route found associated to device.')
        shipment_alice.device = self.device
        shipment_alice.save()

        response = api_client.post(self.url_device, {'payload': signed_tracking_data})
        AssertionHelper.HTTP_204(response)
        assert TrackingData.objects.all().count() == 1

    def test_invalid_jws(self, api_client, shipment_alice_with_device):
        response = api_client.post(self.url_device, {'payload': {'this': 'is not a jws'}})
        AssertionHelper.HTTP_400(response, error='This value does not match the required pattern.')

        response = api_client.post(self.url_device, {'payload': 'neither.is.this'})
        AssertionHelper.HTTP_400(response, error="Invalid JWS: Invalid header string: 'utf-8' codec can't decode byte 0x9d in position 0: invalid start byte")

        response = api_client.post(self.url_device, {'payload': 'or.this'})
        AssertionHelper.HTTP_400(response, error='This value does not match the required pattern.')

        response = api_client.post(self.url_device, {'payload': 'bm9ybm9ybm9y.aXNpc2lz.dGhpc3RoaXN0aGlz'})
        AssertionHelper.HTTP_400(response, error='Invalid JWS: Invalid header string: Expecting value: line 1 column 1 (char 0)')

    def test_bulk_shipment_data(self, api_client, shipment_alice_with_device, tracking_data):
        signed_tracking_data = self.sign_tracking(tracking_data, self.device)
        tracking_data['timestamp'] = (datetime.utcnow() + timedelta(minutes=5)).isoformat()
        signed_tracking_data_two = self.sign_tracking(tracking_data, self.device)

        response = api_client.post(self.url_device, [{'payload': signed_tracking_data},
                                                     {'payload': signed_tracking_data_two}])
        AssertionHelper.HTTP_204(response)
        assert TrackingData.objects.all().count() == 2

    def test_agnostic_authentication(self, api_client, client_bob, client_alice, shipment_alice_with_device,
                                     tracking_data):
        signed_tracking_data = self.sign_tracking(tracking_data, self.device)
        response = api_client.post(self.url_device, {'payload': signed_tracking_data})
        AssertionHelper.HTTP_204(response)
        assert TrackingData.objects.all().count() == 1

        response = client_bob.post(self.url_device, {'payload': signed_tracking_data})
        AssertionHelper.HTTP_204(response)
        assert TrackingData.objects.all().count() == 2

        response = client_alice.post(self.url_device, {'payload': signed_tracking_data})
        AssertionHelper.HTTP_204(response)
        assert TrackingData.objects.all().count() == 3

    def test_invalid_certificate_id(self, api_client, shipment_alice_with_device, tracking_data):
        signed_tracking_data = self.sign_tracking(tracking_data, self.device, certificate_id="NotARealCertificateId")
        response = api_client.post(self.url_device, {'payload': signed_tracking_data})
        AssertionHelper.HTTP_403(response, error='Certificate: NotARealCertificateId, is invalid: Parameter validation '
                                                 'failed:\nInvalid length for parameter certificateId, value: 21, valid range: 64-inf')

        signed_tracking_data = self.sign_tracking(tracking_data, self.device, certificate_id=('a' * 64))
        response = api_client.post(self.url_device, {'payload': signed_tracking_data})
        AssertionHelper.HTTP_403(response, error=f'Certificate: {"a" * 64}, is invalid: An error occurred '
                                                 f'(ResourceNotFoundException) when calling the DescribeCertificate '
                                                 f'operation: The specified resource does not exist')

        self.mocked_iot.update_certificate(certificateId=self.device.certificate_id, newStatus='REVOKED')
        response = api_client.post(self.url_device, {'payload': self.sign_tracking(tracking_data, self.device)})
        AssertionHelper.HTTP_403(response, error=f'Certificate {self.device.certificate_id} is not ACTIVE in IoT for shipment')

        with open('tests/data/cert2.pem', 'r') as cert_file:
            bad_cert = cert_file.read()
        cert_response = self.mocked_iot.register_certificate(
            certificatePem=bad_cert,
            status='ACTIVE'
        )
        signed_tracking_data = self.sign_tracking(tracking_data, self.device, certificate_id=cert_response['certificateId'])
        response = api_client.post(self.url_device, {'payload': signed_tracking_data})
        AssertionHelper.HTTP_403(response,
                                 error=f'Unexpected error: No certificates found for device {self.device.id} in AWS IoT,'
                                       f' occurred while trying to retrieve device: {self.device.id}, from AWS IoT')

    def test_tracking_data_format(self, api_client, shipment_alice_with_device, tracking_data):
        signed_tracking_data = self.sign_tracking({
            'position': {
                'longitude': 83,
                'altitude': 554,
                'source': 'Gps',
                'uncertainty': 92,
                'speed': 34.56
            },
            'version': '1.0.0',
            'timestamp': datetime.utcnow().isoformat()
        }, self.device)

        response = api_client.post(self.url_device, {'payload': signed_tracking_data})
        AssertionHelper.HTTP_400(response, error='This field is required', pointer='latitude')

        signed_tracking_data = self.sign_tracking({
            'position': {
                'latitude': 83,
                'altitude': 554,
                'source': 'Gps',
                'uncertainty': 92,
                'speed': 34.56
            },
            'version': '1.0.0',
            'timestamp': datetime.utcnow().isoformat()
        }, self.device)

        response = api_client.post(self.url_device, {'payload': signed_tracking_data})
        AssertionHelper.HTTP_400(response, error='This field is required', pointer='longitude')

    def test_random_device_id(self, api_client, tracking_data, shipment_alice_with_device):
        signed_tracking_data = self.sign_tracking(tracking_data, self.device)

        response = api_client.post(self.url_random, {'payload': signed_tracking_data})
        AssertionHelper.HTTP_403(response, error='No shipment/route found associated to device.')

        # Does not matter which device id is in the data just the id in the endpoint
        signed_tracking_data = self.sign_tracking(tracking_data, self.device, device_id=random_id())
        response = api_client.post(self.url_device, {'payload': signed_tracking_data})
        AssertionHelper.HTTP_204(response)

    def test_invalid_key(self, api_client, tracking_data, shipment_alice_with_device):
        signed_tracking_data = self.sign_tracking(tracking_data, self.device, key=self.key_pem2)

        response = api_client.post(self.url_device, {'payload': signed_tracking_data})
        AssertionHelper.HTTP_403(response, error='Error validating tracking data JWS: Signature verification failed.')


    def test_update_shipment_device_certificate(self, client_alice, tracking_data, profiles_ids, mocker,
                                                shipment_alice_with_device, mock_successful_wallet_owner_calls,
                                                successful_shipment_create_profiles_assertions):
        mock_device_call = mocker.patch.object(settings.REQUESTS_SESSION, 'get')
        mock_device_call.return_value.status_code = 200

        with open('tests/data/cert.pem', 'r') as cert_file:
            cert_pem = cert_file.read()

        map_describe = {}
        principals = []
        for i in range(0, 4):
            describe = {}
            res = self.mocked_iot.create_keys_and_certificate()
            describe['certificateDescription'] = res
            describe['certificateDescription']['status'] = 'INACTIVE'
            if i == 1:
                expired_certificate = res['certificateId']
            if i == 2:
                describe['certificateDescription']['status'] = 'ACTIVE'
                describe['certificateDescription']['certificatePem'] = cert_pem
                new_active_certificate = res['certificateId']
            map_describe[res['certificateId']] = describe
            principals.append(res['certificateArn'])

        self.device.certificate_id = expired_certificate
        self.device.save()

        def side_effects(**kwargs):
            cert = kwargs['certificateId']
            return map_describe[cert]

        with mock.patch('apps.shipments.serializers.boto3.client') as serial_client, \
                mock.patch('apps.shipments.models.boto3.client') as model_client:
            serial_client = serial_client.return_value
            model_client = model_client.return_value
            serial_client.describe_certificate.side_effect = side_effects
            model_client.list_thing_principals.return_value = {'principals': principals}
            model_client.describe_certificate.side_effect = side_effects

            signed_data = self.sign_tracking(tracking_data, self.device, certificate_id=new_active_certificate)
            response = client_alice.post(self.url_device, data={'payload': signed_data})
            AssertionHelper.HTTP_204(response)
            self.device.refresh_from_db()

            assert self.device.certificate_id == new_active_certificate
            shipment_alice_with_device.device = None
            shipment_alice_with_device.save()

            self.device.certificate_id = expired_certificate
            self.device.save()
            self.device.refresh_from_db()

            response = client_alice.post(self.create_url, data={'device_id': self.device.id, **profiles_ids})
            AssertionHelper.HTTP_202(response)

            self.device.refresh_from_db()
            assert self.device.certificate_id == new_active_certificate
