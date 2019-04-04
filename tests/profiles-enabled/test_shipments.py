import copy
import json
import os
import re
from unittest import mock

import boto3
import httpretty
from datetime import datetime, timezone, timedelta
from dateutil import parser
from django.conf import settings as test_settings
from django.db import transaction
from jose import jws
from moto import mock_iot
from rest_framework import status
from rest_framework.reverse import reverse
from rest_framework.test import APITestCase, force_authenticate, APIClient

from apps.authentication import passive_credentials_auth
from apps.eth.models import EthAction
from apps.iot_client import BotoAWSRequestsAuth
from apps.shipments.models import Shipment, Location, Device, TrackingData, PermissionLink
from apps.shipments.rpc import Load110RPCClient
from apps.utils import random_id
from tests.utils import get_jwt
from tests.utils import replace_variables_in_string, create_form_content, mocked_rpc_response

boto3.setup_default_session()  # https://github.com/spulec/moto/issues/1926

VAULT_ID = 'b715a8ff-9299-4c87-96de-a4b0a4a54509'
CARRIER_WALLET_ID = '3716ff65-3d03-4b65-9fd5-43d15380cff9'
SHIPPER_WALLET_ID = '48381c16-432b-493f-9f8b-54e88a84ec0a'
STORAGE_CRED_ID = '77b72202-5bcd-49f4-9860-bc4ec4fee07b'
DEVICE_ID = '332dc6c8-b89e-449e-a802-0bfe760f83ff'
CERTIFICATE_ID = '230498151c214b788dd97f22b85410a5'
OWNER_ID = '332dc6c8-b89e-449e-a802-0bfe760f83ff'
OWNER_ID_2 = '48381c16-432b-493f-9f8b-54e88a84ec0a'
OWNER_ID_3 = '6165f048-67dc-4265-a231-09ed12afb4e2'
ORGANIZATION_ID = '00000000-0000-0000-0000-000000000001'
LOCATION_NAME = "Test Location Name"
LOCATION_NAME_2 = "Second Test Location Name"
LOCATION_CITY = 'City'
LOCATION_STATE = 'State'
LOCATION_COUNTRY = 'US'
BAD_COUNTRY_CODE = 'XY'
LOCATION_NUMBER = '555-555-5555'

mapbox_url = re.compile(r'https://api.mapbox.com/geocoding/v5/mapbox.places/[\w$\-@&+%,]+.json')
google_url = f'https://maps.googleapis.com/maps/api/geocode/json'


class ShipmentAPITests(APITestCase):
    def setUp(self):
        self.client = APIClient()

        self.token = get_jwt(username='user1@shipchain.io', sub=OWNER_ID, organization_id=ORGANIZATION_ID)
        self.token2 = get_jwt(username='user2@shipchain.io', sub=OWNER_ID_2)
        self.token3 = get_jwt(username='user3@shipchain.io', sub=OWNER_ID_3, organization_id=ORGANIZATION_ID)
        self.user_1 = passive_credentials_auth(self.token)
        self.user_2 = passive_credentials_auth(self.token2)
        self.user_3 = passive_credentials_auth(self.token3)

    def set_user(self, user, token=None):
        self.client.force_authenticate(user=user, token=token)

    def create_shipment(self):
        self.shipments = []
        self.shipments.append(Shipment.objects.create(vault_id=VAULT_ID,
                                                      carrier_wallet_id=CARRIER_WALLET_ID,
                                                      shipper_wallet_id=SHIPPER_WALLET_ID,
                                                      storage_credentials_id=STORAGE_CRED_ID,
                                                      pickup_est="2018-11-10T17:57:05.070419Z",
                                                      owner_id=self.user_1.id))
        self.shipments.append(Shipment.objects.create(vault_id=VAULT_ID,
                                                      carrier_wallet_id=CARRIER_WALLET_ID,
                                                      shipper_wallet_id=SHIPPER_WALLET_ID,
                                                      storage_credentials_id=STORAGE_CRED_ID,
                                                      pickup_est="2018-11-05T17:57:05.070419Z",
                                                      mode_of_transport_code='mode',
                                                      owner_id=self.user_1.id))
        self.shipments.append(Shipment.objects.create(vault_id=VAULT_ID,
                                                      carrier_wallet_id=CARRIER_WALLET_ID,
                                                      shipper_wallet_id=SHIPPER_WALLET_ID,
                                                      storage_credentials_id=STORAGE_CRED_ID,
                                                      pickup_est="2018-11-05T17:57:05.070419Z",
                                                      mode_of_transport_code='mode',
                                                      owner_id=self.user_2.id))

    def create_location(self, **data):
        return Location.objects.create(**data)

    def test_list_empty(self):
        """
        Test listing requires authentication
        """

        # Unauthenticated request should fail with 403
        url = reverse('shipment-list', kwargs={'version': 'v1'})

        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        # Authenticated request should succeed
        self.set_user(self.user_1)

        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        response_data = response.json()

        # No shipments created should return empty array
        self.assertEqual(len(response_data['data']), 0)

    def test_list_populated(self):
        """
        Test listing requires authentication
        """

        # Unauthenticated request should fail with 403
        url = reverse('shipment-list', kwargs={'version': 'v1'})

        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        self.create_shipment()

        # Authenticated request should succeed
        self.set_user(self.user_1)

        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        response_data = response.json()
        self.assertEqual(len(response_data['data']), 2)

    def test_filter(self):
        """
        Test filtering for objects
        """
        # Unauthenticated request should fail with 403
        url = reverse('shipment-list', kwargs={'version': 'v1'})

        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        self.create_shipment()

        # Authenticated request should succeed
        self.set_user(self.user_1)

        response = self.client.get(f'{url}?mode_of_transport_code=mode')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        response_data = response.json()
        self.assertEqual(len(response_data['data']), 1)

        setattr(self.shipments[1], 'ship_to_location', Location.objects.create(name="locat"))
        self.shipments[1].save()

    def test_ordering(self):
        """
        Test filtering for objects
        """
        # Unauthenticated request should fail with 403
        url = reverse('shipment-list', kwargs={'version': 'v1'})

        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        self.create_shipment()

        # Authenticated request should succeed
        self.set_user(self.user_1)

        response = self.client.get(f'{url}?ordering=pickup_est')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        response_data = response.json()
        self.assertEqual(response_data['data'][0]['id'], self.shipments[1].id)

        response = self.client.get(f'{url}?ordering=-pickup_est')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        response_data = response.json()
        self.assertEqual(response_data['data'][0]['id'], self.shipments[0].id)

    @httpretty.activate
    def test_carrier_shipment_access(self):
        """
        Ensure that the owner of a shipment's carrier wallet is able to access and update shipment objects.
        """
        self.create_shipment()
        url = reverse('shipment-detail', kwargs={'version': 'v1', 'pk': self.shipments[0].id})

        httpretty.register_uri(httpretty.GET,
                               f"{test_settings.PROFILES_URL}/api/v1/wallet/{CARRIER_WALLET_ID}/?is_active",
                               body=json.dumps({'good': 'good'}), status=status.HTTP_200_OK)
        httpretty.register_uri(httpretty.GET,
                               f"{test_settings.PROFILES_URL}/api/v1/wallet/{SHIPPER_WALLET_ID}/?is_active",
                               body=json.dumps({'good': 'good'}), status=status.HTTP_200_OK)

        # Unauthenticated request should fail with 403
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        # Authenticated request for shipment owner should succeed
        self.set_user(self.user_1)

        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Authenticated request for shipment's carrier wallet owner should succeed
        self.set_user(self.user_2)

        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Authenticated request to update by shipment's carrier should succeed
        shipment_update, content_type = create_form_content({"carrier_scac": "carrier_scac"})
        response = self.client.patch(url, shipment_update, content_type=content_type)

        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)

        # Authenticated request to delete a shipment by carrier should fail
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        # Authenticated request by owner of a shipment to delete should succeed
        self.set_user(self.user_1)
        response = self.client.delete(url)

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)


    @mock_iot
    def test_add_tracking_data(self):
        from apps.rpc_client import requests
        from tests.utils import mocked_rpc_response

        device_id = 'adfc1e4c-7e61-4aee-b6f5-4d8b95a7ec75'

        # Create device 'thing'
        iot = boto3.client('iot', region_name='us-east-1')
        iot.create_thing(
            thingName=device_id
        )

        # Load device cert into AWS
        with open('tests/data/cert.pem', 'r') as cert_file:
            cert_pem = cert_file.read()
        cert_response = iot.register_certificate(
            certificatePem=cert_pem,
            status='ACTIVE'
        )
        certificate_id = cert_response['certificateId']

        # Set device for Shipment
        with mock.patch.object(requests.Session, 'post') as mock_method:
            mock_method.return_value = mocked_rpc_response({
                "jsonrpc": "2.0",
                "result": {
                    "success": True,
                    "vault_id": "TEST_VAULT_ID"
                }
            })
            self.create_shipment()
            self.shipments[0].device = Device.objects.create(
                id=device_id,
                certificate_id=certificate_id
            )

            mock_method.return_value = mocked_rpc_response({
                "jsonrpc": "2.0",
                "result": {
                    "success": True,
                    "vault_signed": {'hash': "TEST_VAULT_SIGNATURE"}
                }
            })
            self.shipments[0].save()

            url = reverse('shipment-tracking', kwargs={'version': 'v1', 'pk': self.shipments[0].id})

            track_dic = {
                'position': {
                    'latitude': 75.0587610,
                    'longitude': -35.628643,
                    'altitude': 554,
                    'source': 'Gps',
                    'uncertainty': 92,
                    'speed': 34
                },
                'version': '1.0.0',
                'device_id': 'adfc1e4c-7e61-4aee-b6f5-4d8b95a7ec75',
                'timestamp': '2018-09-18T15:02:30.563847+00:00'
            }
            with open('tests/data/eckey.pem', 'r') as key_file:
                key_pem = key_file.read()
            signed_data = jws.sign(track_dic, key=key_pem, headers={'kid': certificate_id}, algorithm='ES256')

            # Send tracking update
            response = self.client.post(url, {'payload': signed_data}, format='json')
            self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

            # Tracking data in db
            data_from_db = TrackingData.objects.all()
            self.assertTrue(data_from_db.count(), 1)
            self.assertEqual(data_from_db[0].device.id, track_dic['device_id'])
            self.assertTrue(isinstance(data_from_db[0].shipment, Shipment))
            self.assertEqual(data_from_db[0].latitude, track_dic['position']['latitude'])

            # Bulk add tracking data
            track_dic2 = copy.deepcopy(track_dic)
            track_dic2['position']['speed'] = 30
            track_dic2['timestamp'] = '2018-09-18T15:02:31.563847+00:00'
            signed_data2 = jws.sign(track_dic2, key=key_pem, headers={'kid': certificate_id}, algorithm='ES256')
            list_payload = [{'payload': signed_data}, {'payload': signed_data2}]
            response = self.client.post(url, list_payload, format='json')
            self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

            # Get tracking data
            response = self.client.get(url)

            # Unauthenticated request should fail
            self.assertEqual(response.status_code, 403)

            # Authenticated request should succeed
            self.set_user(self.user_1)
            response = self.client.get(url)
            self.assertTrue(response.status_code, status.HTTP_200_OK)
            data = json.loads(response.content)['data']
            self.assertEqual(data['type'], 'FeatureCollection')

            # Add second tracking data
            track_dic_2 = copy.deepcopy(track_dic)
            track_dic_2['timestamp'] = '2018-09-18T15:02:20.563847+00:00'
            track_dic_2['position']['latitude'] -= 2
            track_dic_2['position']['longitude'] += 2

            signed_data = jws.sign(track_dic_2, key=key_pem, headers={'kid': certificate_id}, algorithm='ES256')

            # Send second tracking data
            response = self.client.post(url, {'payload': signed_data}, format='json')
            self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

            # Test second tracking data
            response = self.client.get(url)
            self.assertTrue(response.status_code, status.HTTP_200_OK)
            data = json.loads(response.content)['data']
            self.assertEqual(len(data['features']), 4)

            # We expect the second point data to be the first in LineString
            # since it has been  generated first. See timestamp values
            pos = track_dic_2['position']
            self.assertEqual(data['features'][0]['geometry']['coordinates'], [pos['longitude'], pos['latitude']])

            # Get data as point
            url_as_point = url + '?as_point'
            response = self.client.get(url_as_point)
            self.assertTrue(response.status_code, status.HTTP_200_OK)
            data = json.loads(response.content)['data']
            self.assertTrue(isinstance(data['features'], list))
            self.assertEqual(data['features'][0]['geometry']['type'], 'Point')

            # Certificate ID not in AWS
            signed_data = jws.sign(track_dic, key=key_pem, headers={'kid': 'notarealcertificateid'}, algorithm='ES256')
            response = self.client.post(url, {'payload': signed_data}, format='json')
            self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

            # Signed by a different key
            with open('tests/data/eckey2.pem', 'r') as key_file:
                bad_key = key_file.read()
            signed_data = jws.sign(track_dic, key=bad_key, headers={'kid': certificate_id}, algorithm='ES256')
            response = self.client.post(url, {'payload': signed_data}, format='json')
            self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

            # Data from a different device
            bad_device_id = 'bdfc1e4c-7e61-4aee-b6f5-4d8b95a7ec76'
            iot = boto3.client('iot', region_name='us-east-1')
            iot.create_thing(
                thingName=bad_device_id
            )
            with open('tests/data/cert2.pem', 'r') as cert_file:
                bad_cert = cert_file.read()
            cert_response = iot.register_certificate(
                certificatePem=bad_cert,
                status='ACTIVE'
            )
            bad_cert_id = cert_response['certificateId']
            signed_data = jws.sign(track_dic, key=bad_key, headers={'kid': bad_cert_id}, algorithm='ES256')
            response = self.client.post(url, {'payload': signed_data}, format='json')
            self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

            # Invalid JWS
            response = self.client.post(url, {'payload': {'this': 'is not a jws'}}, format='json')
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
            response = self.client.post(url, {'payload': 'neither.is.this'}, format='json')
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
            response = self.client.post(url, {'payload': 'or.this'}, format='json')
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
            response = self.client.post(url, {'payload': 'bm9ybm9ybm9y.aXNpc2lz.dGhpc3RoaXN0aGlz'}, format='json')
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

            # Certificate not ACTIVE
            iot.update_certificate(certificateId=certificate_id, newStatus='REVOKED')
            signed_data = jws.sign(track_dic, key=key_pem, headers={'kid': certificate_id}, algorithm='ES256')
            response = self.client.post(url, {'payload': signed_data}, format='json')
            self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
            iot.update_certificate(certificateId=certificate_id, newStatus='ACTIVE')

            # Device not assigned to shipment
            self.shipments[0].device = None
            self.shipments[0].save()
            response = self.client.post(url, {'payload': signed_data}, format='json')
            self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_shipment_update(self):
        self.create_shipment()
        url = reverse('shipments-detail', kwargs={'version': 'v1', 'pk': self.shipments[0].id})

        successful_delivery_act, content_type = create_form_content({'delivery_act': datetime.now()})
        datetime_aware_delivery_act, content_type = create_form_content({'delivery_act': "2018-08-22T17:44:39.874352"})
        unsuccessful_delivery_act, content_type = create_form_content({'delivery_act': datetime.now() +
                                                                                       timedelta(days=1)})

        # Unauthenticated response should fail
        response = self.client.patch(url, successful_delivery_act, content_type=content_type)
        assert response.status_code == status.HTTP_403_FORBIDDEN

        # Authenticated account with invalid delivery_act should fail
        self.set_user(self.user_1)
        response = self.client.patch(url, unsuccessful_delivery_act, content_type=content_type)
        assert response.status_code == status.HTTP_400_BAD_REQUEST

        # Authenticated account with valid delivery_act should succeed
        response = self.client.patch(url, successful_delivery_act, content_type=content_type)
        assert response.status_code == status.HTTP_200_OK

        # Authenticated account with valid datetime aware delivery_act should fail
        response = self.client.patch(url, datetime_aware_delivery_act, content_type=content_type)
        assert response.status_code == status.HTTP_200_OK

    def test_update_shipment_device_certificate(self):
        """
        The shipment's device certificate has been updated but the the old certificate is still attached to the device.
        when we post new tracking data, we should be able to track and retrieve the new certificate in aws IoT and
        attach it to the device
        """
        from apps.rpc_client import requests
        from tests.utils import mocked_rpc_response

        with mock_iot():
            iot = boto3.client('iot', region_name='us-east-1')

            device_id = 'adfc1e4c-7e61-4aee-b6f5-4d8b95a7ec75'

            with open('tests/data/cert.pem', 'r') as cert_file:
                cert_pem = cert_file.read()

            map_describe = {}
            principals = []
            expired_certificate = None
            new_active_certificate = None
            for i in range(0, 4):
                describe = {}
                res = iot.create_keys_and_certificate()
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

        # Set device for Shipment
        with mock.patch.object(requests.Session, 'post') as mock_method:
            mock_method.return_value = mocked_rpc_response({
                "jsonrpc": "2.0",
                "result": {
                    "success": True,
                    "vault_id": "TEST_VAULT_ID"
                }
            })
            self.create_shipment()
            self.shipments[0].device = Device.objects.create(
                id=device_id,
                certificate_id=expired_certificate
            )

            mock_method.return_value = mocked_rpc_response({
                "jsonrpc": "2.0",
                "result": {
                    "success": True,
                    "vault_signed": {'hash': "TEST_VAULT_SIGNATURE"}
                }
            })

            with mock.patch('apps.iot_client.requests.Session.put') as mocked:
                mocked.return_value = mocked_rpc_response({'data': {
                    'shipmentId': self.shipments[0].id
                }})
                self.shipments[0].save()

        url = reverse('shipment-tracking', kwargs={'version': 'v1', 'pk': self.shipments[0].id})

        track_dic = {
            'position': {
                'latitude': 75.0587610,
                'longitude': -35.628643,
                'altitude': 554,
                'source': 'Gps',
                'uncertainty': 92,
                'speed': 34
            },
            'version': '1.0.0',
            'device_id': 'adfc1e4c-7e61-4aee-b6f5-4d8b95a7ec75',
            'timestamp': '2018-09-18T15:02:30.563847+00:00'
        }

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

            with open('tests/data/eckey.pem', 'r') as key_file:
                key_pem = key_file.read()
            signed_data = jws.sign(track_dic, key=key_pem, headers={'kid': new_active_certificate}, algorithm='ES256')

            # Send tracking data
            response = self.client.post(url, {'payload': signed_data}, format='json')
            self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
            # The new certificate should be attached to the shipment's device
            device = self.shipments[0].device
            device.refresh_from_db()
            self.assertEqual(device.certificate_id, new_active_certificate)

            # Creating a new shipment with a device for which the certificate has expired and a new one has been issued
            self.shipments[0].device = None
            with mock.patch('apps.iot_client.requests.Session.put') as mocked:
                mocked.return_value = mocked_rpc_response({'data': {
                    'shipmentId': None
                }})
                self.shipments[0].save()
            device.certificate_id = expired_certificate
            device.save()
            device.refresh_from_db()

            post_data = {
                'device_id': device.id,
                'vault_id': VAULT_ID,
                'carrier_wallet_id': CARRIER_WALLET_ID,
                'shipper_wallet_id': SHIPPER_WALLET_ID,
                'storage_credentials_id': STORAGE_CRED_ID
            }

            url = reverse('shipment-list', kwargs={'version': 'v1'})
            self.set_user(self.user_1)

            with mock.patch('apps.shipments.serializers.ShipmentCreateSerializer.validate_shipper_wallet_id') as mock_wallet_validation, \
                    mock.patch('apps.shipments.serializers.ShipmentCreateSerializer.validate_storage_credentials_id') as mock_storage_validation, \
                    mock.patch.object(requests.Session, 'get') as mock_method:

                # Instead of httpretty, we mock the device's profile validation
                mock_method.return_value.status_code = status.HTTP_200_OK

                mock_wallet_validation.return_value = SHIPPER_WALLET_ID
                mock_storage_validation.return_value = STORAGE_CRED_ID

                with mock.patch('apps.iot_client.requests.Session.put') as mocked:
                    mocked.return_value = mocked_rpc_response({'data': {
                        'shipmentId': 'dunno yet'
                    }})
                    response = self.client.post(url, post_data, format='json')
                self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)

                # The new certificate should be attached to the shipment's device
                device.refresh_from_db()
                self.assertEqual(device.certificate_id, new_active_certificate)
                data = response.json()['data']
                self.assertEqual(device.shipment.id, data['id'])

    @httpretty.activate
    def test_create(self):
        url = reverse('shipment-list', kwargs={'version': 'v1'})

        # Unauthenticated request should fail with 403
        response = self.client.patch(url, '{}', content_type='application/vnd.api+json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        parameters = {
            '_vault_id': VAULT_ID,
            '_vault_uri': 's3://bucket/' + VAULT_ID,
            '_carrier_wallet_id': CARRIER_WALLET_ID,
            '_shipper_wallet_id': SHIPPER_WALLET_ID,
            '_storage_credentials_id': STORAGE_CRED_ID,
            '_async_hash': 'txHash'
        }

        post_data = '''
            {
              "data": {
                "type": "Shipment",
                "attributes": {
                  "carrier_wallet_id": "<<_carrier_wallet_id>>",
                  "shipper_wallet_id": "<<_shipper_wallet_id>>",
                  "storage_credentials_id": "<<_storage_credentials_id>>"
                }
              }
            }
        '''

        # Mock RPC calls
        mock_shipment_rpc_client = Load110RPCClient

        mock_shipment_rpc_client.create_vault = mock.Mock(return_value=(parameters['_vault_id'], parameters['_vault_uri']))
        mock_shipment_rpc_client.add_shipment_data = mock.Mock(return_value={'hash': 'txHash'})
        mock_shipment_rpc_client.create_shipment_transaction = mock.Mock(return_value=('version', {}))
        mock_shipment_rpc_client.create_shipment_transaction.__qualname__ = 'ShipmentRPCClient.create_shipment_transaction'
        mock_shipment_rpc_client.sign_transaction = mock.Mock(return_value=({}, 'txHash'))
        mock_shipment_rpc_client.update_vault_hash_transaction = mock.Mock(return_value=({}))
        mock_shipment_rpc_client.update_vault_hash_transaction.__qualname__ = 'ShipmentRPCClient.set_vault_hash_tx'
        mock_shipment_rpc_client.send_transaction = mock.Mock(return_value={
            "blockHash": "0xccb595947a121e37df8bf689c3f88c6d9c7fb56070c9afda38551540f9e231f7",
            "blockNumber": 15,
            "contractAddress": None,
            "cumulativeGasUsed": 138090,
            "from": "0x13b1eebb31a1aa2ecaa2ad9e7455df2f717f2143",
            "gasUsed": 138090,
            "logs": [],
            "logsBloom": "0x0000000000",
            "status": True,
            "to": "0x25ff5dc79a7c4e34254ff0f4a19d69e491201dd3",
            "transactionHash": parameters['_async_hash'],
            "transactionIndex": 0
        })

        # Authenticated request should succeed
        self.set_user(self.user_1, self.token)

        post_data = replace_variables_in_string(post_data, parameters)

        httpretty.register_uri(httpretty.GET,
                               f"{test_settings.PROFILES_URL}/api/v1/wallet/{parameters['_shipper_wallet_id']}/",
                               body=json.dumps({'good': 'good'}), status=status.HTTP_200_OK)
        httpretty.register_uri(httpretty.GET,
                               f"{test_settings.PROFILES_URL}/api/v1/storage_credentials/{parameters['_storage_credentials_id']}/",

                               body=json.dumps({'good': 'good'}), status=status.HTTP_200_OK)

        response = self.client.post(url, post_data, content_type='application/vnd.api+json')
        force_authenticate(response, user=self.user_1, token=self.token)

        response_data = response.json()['data']
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        self.assertEqual(response_data['attributes']['carrier_wallet_id'], parameters['_carrier_wallet_id'])
        self.assertEqual(response_data['attributes']['shipper_wallet_id'], parameters['_shipper_wallet_id'])
        self.assertEqual(response_data['attributes']['storage_credentials_id'], parameters['_storage_credentials_id'])
        self.assertEqual(response_data['attributes']['vault_id'], parameters['_vault_id'])
        self.assertIsNotNone(response_data['meta']['async_job_id'])

        httpretty.register_uri(httpretty.GET,
                               f"{test_settings.PROFILES_URL}/api/v1/wallet/{parameters['_shipper_wallet_id']}/",
                               body=json.dumps({'good': 'good'}), status=status.HTTP_200_OK)
        httpretty.register_uri(httpretty.GET,
                               f"{test_settings.PROFILES_URL}/api/v1/storage_credentials/{parameters['_storage_credentials_id']}/",
                               body=json.dumps({'bad': 'bad'}), status=status.HTTP_400_BAD_REQUEST)

        response = self.client.post(url, post_data, content_type='application/vnd.api+json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        httpretty.register_uri(httpretty.GET,
                               f"{test_settings.PROFILES_URL}/api/v1/wallet/{parameters['_shipper_wallet_id']}/",
                               body=json.dumps({'bad': 'bad'}), status=status.HTTP_400_BAD_REQUEST)
        httpretty.register_uri(httpretty.GET,
                               f"{test_settings.PROFILES_URL}/api/v1/storage_credentials/{parameters['_storage_credentials_id']}/",
                               body=json.dumps({'good': 'good'}), status=status.HTTP_200_OK)

        response = self.client.post(url, post_data, content_type='application/vnd.api+json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    @httpretty.activate
    def test_organization_sharing(self):
        url = reverse('shipment-list', kwargs={'version': 'v1'})

        post_data = {
            'carrier_wallet_id': CARRIER_WALLET_ID,
            'shipper_wallet_id': SHIPPER_WALLET_ID,
            'storage_credentials_id': STORAGE_CRED_ID
        }

        # Mock RPC calls
        mock_shipment_rpc_client = Load110RPCClient
        mock_shipment_rpc_client.create_vault = mock.Mock(return_value=(VAULT_ID, 's3://bucket/' + VAULT_ID))
        mock_shipment_rpc_client.add_shipment_data = mock.Mock(return_value={'hash': 'txHash'})
        mock_shipment_rpc_client.create_shipment_transaction = mock.Mock(return_value=('version', {}))
        mock_shipment_rpc_client.create_shipment_transaction.__qualname__ = 'ShipmentRPCClient.create_shipment_transaction'
        mock_shipment_rpc_client.sign_transaction = mock.Mock(return_value=({}, 'txHash'))
        mock_shipment_rpc_client.update_vault_hash_transaction = mock.Mock(return_value=({}))
        mock_shipment_rpc_client.update_vault_hash_transaction.__qualname__ = 'ShipmentRPCClient.set_vault_hash_tx'
        mock_shipment_rpc_client.send_transaction = mock.Mock(return_value={
            "blockHash": "0xccb595947a121e37df8bf689c3f88c6d9c7fb56070c9afda38551540f9e231f7",
            "blockNumber": 15,
            "contractAddress": None,
            "cumulativeGasUsed": 138090,
            "from": "0x13b1eebb31a1aa2ecaa2ad9e7455df2f717f2143",
            "gasUsed": 138090,
            "logs": [],
            "logsBloom": "0x0000000000",
            "status": True,
            "to": "0x25ff5dc79a7c4e34254ff0f4a19d69e491201dd3",
            "transactionHash": '0x753eeef766142c4a1f0060a7aa51da02a44dccb4db4ccd02887c9d38073af4ba',
            "transactionIndex": 0
        })

        # Mock profiles calls
        httpretty.register_uri(httpretty.GET,
                               f"{test_settings.PROFILES_URL}/api/v1/wallet/{SHIPPER_WALLET_ID}/",
                               status=status.HTTP_200_OK)
        httpretty.register_uri(httpretty.GET,
                               f"{test_settings.PROFILES_URL}/api/v1/storage_credentials/{STORAGE_CRED_ID}/",
                               status=status.HTTP_200_OK)

        # Create shipment with first user
        self.set_user(self.user_1, self.token)
        response = self.client.post(url, post_data, format='json')

        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        shipment_id = response.json()['data']['id']

        # Assert that another user in the same org can also see the created shipment
        self.set_user(self.user_3, self.token3)
        url = reverse('shipment-detail', kwargs={'version': 'v1', 'pk': shipment_id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    @httpretty.activate
    def test_create_with_location(self):
        url = reverse('shipment-list', kwargs={'version': 'v1'})

        # Unauthenticated request should fail with 403
        response = self.client.post(url, '{}', content_type='application/vnd.api+json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        google_obj = {
            'results': [{'address_components': [{'types': []}], 'geometry': {'location': {'lat': 12, 'lng': 23}}}]}
        mapbox_obj = {'features': [{'place_type': [{'types': []}], 'geometry': {'coordinates': [23, 12]}}]}

        httpretty.register_uri(httpretty.GET, google_url, body=json.dumps(google_obj))
        httpretty.register_uri(httpretty.GET, mapbox_url, body=json.dumps(mapbox_obj))

        # Authenticated request should succeed using mapbox (if exists)
        self.set_user(self.user_1, self.token)

        parameters = {
            '_vault_id': VAULT_ID,
            '_vault_uri': 's3://bucket/' + VAULT_ID,
            '_carrier_wallet_id': CARRIER_WALLET_ID,
            '_shipper_wallet_id': SHIPPER_WALLET_ID,
            '_storage_credentials_id': STORAGE_CRED_ID,
            '_async_hash': 'txHash',
            '_ship_from_location_city': LOCATION_CITY,
            '_ship_from_location_state': LOCATION_STATE,
            '_ship_from_location_name': LOCATION_NAME,
            '_ship_to_location_name': LOCATION_NAME_2,
            '_ship_to_location_city': LOCATION_CITY,
            '_ship_to_location_state': LOCATION_STATE,
        }

        one_location, content_type = create_form_content({
                                                          'carrier_wallet_id': CARRIER_WALLET_ID,
                                                          'shipper_wallet_id': SHIPPER_WALLET_ID,
                                                          'storage_credentials_id': STORAGE_CRED_ID,
                                                          'ship_from_location.name': LOCATION_NAME,
                                                          'ship_from_location.city': LOCATION_CITY,
                                                          'ship_from_location.state': LOCATION_STATE,
                                                          })

        two_locations, content_type = create_form_content({
                                                           'carrier_wallet_id': CARRIER_WALLET_ID,
                                                           'shipper_wallet_id': SHIPPER_WALLET_ID,
                                                           'storage_credentials_id': STORAGE_CRED_ID,
                                                           'ship_from_location.name': LOCATION_NAME,
                                                           'ship_from_location.city': LOCATION_CITY,
                                                           'ship_from_location.state': LOCATION_STATE,
                                                           'ship_to_location.name': LOCATION_NAME_2,
                                                           'ship_to_location.city': LOCATION_CITY,
                                                           'ship_to_location.state': LOCATION_STATE,
                                                           })

        # Mock RPC calls
        mock_shipment_rpc_client = Load110RPCClient

        mock_shipment_rpc_client.create_vault = mock.Mock(return_value=(parameters['_vault_id'], parameters['_vault_uri']))
        mock_shipment_rpc_client.add_shipment_data = mock.Mock(return_value={'hash': 'txHash'})
        mock_shipment_rpc_client.create_shipment_transaction = mock.Mock(return_value=('version', {}))
        mock_shipment_rpc_client.create_shipment_transaction.__qualname__ = 'ShipmentRPCClient.create_shipment_transaction'
        mock_shipment_rpc_client.sign_transaction = mock.Mock(return_value=({}, 'txHash'))
        mock_shipment_rpc_client.update_vault_hash_transaction = mock.Mock(return_value=({}))
        mock_shipment_rpc_client.update_vault_hash_transaction.__qualname__ = 'ShipmentRPCClient.set_vault_hash_tx'
        mock_shipment_rpc_client.send_transaction = mock.Mock(return_value={
            "blockHash": "0xccb595947a121e37df8bf689c3f88c6d9c7fb56070c9afda38551540f9e231f7",
            "blockNumber": 15,
            "contractAddress": None,
            "cumulativeGasUsed": 138090,
            "from": "0x13b1eebb31a1aa2ecaa2ad9e7455df2f717f2143",
            "gasUsed": 138090,
            "logs": [],
            "logsBloom": "0x0000000000",
            "status": True,
            "to": "0x25ff5dc79a7c4e34254ff0f4a19d69e491201dd3",
            "transactionHash": parameters['_async_hash'],
            "transactionIndex": 0
        })

        httpretty.register_uri(httpretty.GET,
                               f"{test_settings.PROFILES_URL}/api/v1/wallet/{parameters['_shipper_wallet_id']}/",
                               body=json.dumps({'good': 'good'}), status=status.HTTP_200_OK)
        httpretty.register_uri(httpretty.GET,
                               f"{test_settings.PROFILES_URL}/api/v1/storage_credentials/{parameters['_storage_credentials_id']}/",
                               body=json.dumps({'good': 'good'}), status=status.HTTP_200_OK)

        response = self.client.post(url, one_location, content_type=content_type)

        force_authenticate(response, user=self.user_1, token=self.token)
        response_data = response.json()['data']
        response_included = response.json()['included']
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        self.assertEqual(response_data['attributes']['carrier_wallet_id'], parameters['_carrier_wallet_id'])
        self.assertEqual(response_data['attributes']['shipper_wallet_id'], parameters['_shipper_wallet_id'])
        self.assertEqual(response_data['attributes']['storage_credentials_id'],
                         parameters['_storage_credentials_id'])
        self.assertEqual(response_data['attributes']['vault_id'], parameters['_vault_id'])
        self.assertIsNotNone(response_data['meta']['async_job_id'])

        self.assertIsNotNone(response_data['relationships']['ship_from_location']['data'])
        self.assertEqual(len(response_included), 2)
        ship_from_location = Location.objects.get(id=response_data['relationships']['ship_from_location']['data']['id'])
        self.assertEqual(ship_from_location.city, parameters['_ship_from_location_city'])
        self.assertEqual(ship_from_location.state, parameters['_ship_from_location_state'])
        self.assertEqual(ship_from_location.name, parameters['_ship_from_location_name'])
        self.assertEqual(ship_from_location.geometry.coords, (23.0, 12.0))

        # Authenticated request should succeed using mapbox in creating two locations (if exists)
        response = self.client.post(url, two_locations, content_type=content_type)
        force_authenticate(response, token=self.token)
        response_data = response.json()['data']
        response_included = response.json()['included']
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        self.assertEqual(response_data['attributes']['carrier_wallet_id'], parameters['_carrier_wallet_id'])
        self.assertEqual(response_data['attributes']['shipper_wallet_id'], parameters['_shipper_wallet_id'])
        self.assertEqual(response_data['attributes']['storage_credentials_id'],
                         parameters['_storage_credentials_id'])
        self.assertEqual(response_data['attributes']['vault_id'], parameters['_vault_id'])
        self.assertIsNotNone(response_data['meta']['async_job_id'])

        self.assertIsNotNone(response_data['relationships']['ship_from_location']['data'])
        ship_from_location = Location.objects.get(id=response_data['relationships']['ship_from_location']['data']['id'])
        self.assertEqual(ship_from_location.city, parameters['_ship_from_location_city'])
        self.assertEqual(ship_from_location.state, parameters['_ship_from_location_state'])
        self.assertEqual(ship_from_location.name, parameters['_ship_from_location_name'])
        self.assertEqual(ship_from_location.geometry.coords, (23.0, 12.0))

        self.assertIsNotNone(response_data['relationships']['ship_to_location']['data'])
        self.assertEqual(len(response_included), 3)
        ship_to_location = Location.objects.get(id=response_data['relationships']['ship_to_location']['data']['id'])
        self.assertEqual(ship_to_location.city, parameters['_ship_to_location_city'])
        self.assertEqual(ship_to_location.state, parameters['_ship_to_location_state'])
        self.assertEqual(ship_to_location.name, parameters['_ship_to_location_name'])
        self.assertEqual(ship_to_location.geometry.coords, (23.0, 12.0))

        # Authenticated request should succeed using google
        mapbox_access_token = None

        response = self.client.post(url, one_location, content_type=content_type)
        force_authenticate(response, user=self.user_1, token=self.token)
        response_data = response.json()['data']
        response_included = response.json()['included']
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        self.assertEqual(response_data['attributes']['carrier_wallet_id'], parameters['_carrier_wallet_id'])
        self.assertEqual(response_data['attributes']['shipper_wallet_id'], parameters['_shipper_wallet_id'])
        self.assertEqual(response_data['attributes']['storage_credentials_id'],
                         parameters['_storage_credentials_id'])
        self.assertEqual(response_data['attributes']['vault_id'], parameters['_vault_id'])
        self.assertIsNotNone(response_data['meta']['async_job_id'])

        self.assertIsNotNone(response_data['relationships']['ship_from_location']['data'])
        self.assertEqual(len(response_included), 2)
        ship_from_location = Location.objects.get(id=response_data['relationships']['ship_from_location']['data']['id'])
        self.assertEqual(ship_from_location.city, parameters['_ship_from_location_city'])
        self.assertEqual(ship_from_location.state, parameters['_ship_from_location_state'])
        self.assertEqual(ship_from_location.name, parameters['_ship_from_location_name'])
        self.assertEqual(ship_from_location.geometry.coords, (23.0, 12.0))

        # Authenticated request should succeed using google in creating two locations
        response = self.client.post(url, two_locations, content_type=content_type)
        force_authenticate(response, user=self.user_1, token=self.token)
        response_data = response.json()['data']
        response_included = response.json()['included']
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        self.assertEqual(response_data['attributes']['carrier_wallet_id'], parameters['_carrier_wallet_id'])
        self.assertEqual(response_data['attributes']['shipper_wallet_id'], parameters['_shipper_wallet_id'])
        self.assertEqual(response_data['attributes']['storage_credentials_id'],
                         parameters['_storage_credentials_id'])
        self.assertEqual(response_data['attributes']['vault_id'], parameters['_vault_id'])
        self.assertIsNotNone(response_data['meta']['async_job_id'])

        self.assertIsNotNone(response_data['relationships']['ship_from_location']['data'])
        ship_from_location = Location.objects.get(id=response_data['relationships']['ship_from_location']['data']['id'])
        self.assertEqual(ship_from_location.city, parameters['_ship_from_location_city'])
        self.assertEqual(ship_from_location.state, parameters['_ship_from_location_state'])
        self.assertEqual(ship_from_location.name, parameters['_ship_from_location_name'])
        self.assertEqual(ship_from_location.geometry.coords, (23.0, 12.0))

        self.assertIsNotNone(response_data['relationships']['ship_to_location']['data'])
        self.assertEqual(len(response_included), 3)
        ship_to_location = Location.objects.get(id=response_data['relationships']['ship_to_location']['data']['id'])
        self.assertEqual(ship_to_location.city, parameters['_ship_to_location_city'])
        self.assertEqual(ship_to_location.state, parameters['_ship_to_location_state'])
        self.assertEqual(ship_to_location.name, parameters['_ship_to_location_name'])
        self.assertEqual(ship_to_location.geometry.coords, (23.0, 12.0))

        httpretty.register_uri(httpretty.GET,
                               f"{test_settings.PROFILES_URL}/api/v1/wallet/{parameters['_shipper_wallet_id']}/",
                               body=json.dumps({'good': 'good'}), status=status.HTTP_200_OK)
        httpretty.register_uri(httpretty.GET,
                               f"{test_settings.PROFILES_URL}/api/v1/storage_credentials/{parameters['_storage_credentials_id']}/",
                               body=json.dumps({'bad': 'bad'}), status=status.HTTP_400_BAD_REQUEST)

        response = self.client.post(url, one_location, content_type=content_type)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        httpretty.register_uri(httpretty.GET,
                               f"{test_settings.PROFILES_URL}/api/v1/wallet/{parameters['_shipper_wallet_id']}/",
                               body=json.dumps({'bad': 'bad'}), status=status.HTTP_400_BAD_REQUEST)
        httpretty.register_uri(httpretty.GET,
                               f"{test_settings.PROFILES_URL}/api/v1/storage_credentials/{parameters['_storage_credentials_id']}/",
                               body=json.dumps({'good': 'good'}), status=status.HTTP_200_OK)

        response = self.client.post(url, one_location, content_type=content_type)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        # Test query parameters
        response = self.client.get(f'{url}?ship_to_location__name={LOCATION_NAME_2}')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        response_data = response.json()
        self.assertEqual(len(response_data['data']), 2)

        response = self.client.get(f'{url}?has_ship_to_location=true')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        response_data = response.json()

        self.assertEqual(len(response_data['data']), 2)

    def test_get_device_request_url(self):

        _shipment_id = 'b715a8ff-9299-4c87-96de-a4b0a4a54509'
        _vault_id = '01fc36c4-63e5-4c02-943a-b52cd25b235b'
        shipment = Shipment.objects.create(id=_shipment_id, vault_id=_vault_id)

        profiles_url = shipment.get_device_request_url()

        # http://INTENTIONALLY_DISCONNECTED:9999/api/v1/device/?on_shipment=b715a8ff-9299-4c87-96de-a4b0a4a54509
        self.assertIn(test_settings.PROFILES_URL, profiles_url)
        self.assertIn(f"?on_shipment={_shipment_id}", profiles_url)

    def test_shipment_update(self):
        self.create_shipment()
        url = reverse('shipment-detail', kwargs={'version': 'v1', 'pk': self.shipments[0].id})

        # Unauthenticated request should fail with 403
        response = self.client.put(url, '{}', content_type='application/vnd.api+json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        parameters = {
            '_vault_id': VAULT_ID,
            '_carrier_wallet_id': CARRIER_WALLET_ID,
            '_shipper_wallet_id': SHIPPER_WALLET_ID,
            '_storage_credentials_id': STORAGE_CRED_ID,
            '_async_hash': 'txHash',
            '_shipment_id': self.shipments[0].id,
            '_carriers_scac': 'test_scac'
        }

        post_data = '''
                    {
                      "data": {
                        "type": "Shipment",
                        "id": "<<_shipment_id>>",
                        "attributes": {
                          "carriers_scac": "test_scac"
                        }
                      }
                    }
                '''

        # Mock RPC calls
        mock_shipment_rpc_client = Load110RPCClient

        mock_shipment_rpc_client.add_shipment_data = mock.Mock(return_value={"hash": "txHash"})
        mock_shipment_rpc_client.sign_transaction = mock.Mock(return_value=({}, 'txHash'))
        mock_shipment_rpc_client.update_vault_hash_transaction = mock.Mock(return_value=({}))
        mock_shipment_rpc_client.update_vault_hash_transaction.__qualname__ = 'ShipmentRPCClient.set_vault_hash_tx'
        mock_shipment_rpc_client.send_transaction = mock.Mock(return_value={
            "blockHash": "0xccb595947a121e37df8bf689c3f88c6d9c7fb56070c9afda38551540f9e231f7",
            "blockNumber": 15,
            "contractAddress": None,
            "cumulativeGasUsed": 138090,
            "from": "0x13b1eebb31a1aa2ecaa2ad9e7455df2f717f2143",
            "gasUsed": 138090,
            "logs": [],
            "logsBloom": "0x0000000000",
            "status": True,
            "to": "0x25ff5dc79a7c4e34254ff0f4a19d69e491201dd3",
            "transactionHash": parameters['_async_hash'],
            "transactionIndex": 0
        })

        # Authenticated request using put method should fail
        self.set_user(self.user_1)

        post_data = replace_variables_in_string(post_data, parameters)
        response = self.client.put(url, post_data, content_type='application/vnd.api+json')
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

        # Authenticated request should succeed using patch should succeed
        post_data = replace_variables_in_string(post_data, parameters)
        response = self.client.patch(url, post_data, content_type='application/vnd.api+json')

        response_data = response.json()['data']
        self.assertEqual(response_data['attributes']['carrier_wallet_id'], parameters['_carrier_wallet_id'])
        self.assertEqual(response_data['attributes']['shipper_wallet_id'], parameters['_shipper_wallet_id'])
        self.assertEqual(response_data['attributes']['storage_credentials_id'],
                         parameters['_storage_credentials_id'])
        self.assertEqual(response_data['attributes']['carriers_scac'], parameters['_carriers_scac'])
        self.assertEqual(response_data['attributes']['vault_id'], parameters['_vault_id'])
        self.assertIsNotNone(response_data['meta']['async_job_id'])

    @httpretty.activate
    def test_update_with_location(self):
        self.create_shipment()
        url = reverse('shipment-detail', kwargs={'version': 'v1', 'pk': self.shipments[0].id})

        # Unauthenticated request should fail with 403
        response = self.client.patch(url, '{}', content_type='application/vnd.api+json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        google_obj = {
            'results': [{'address_components': [{'types': []}], 'geometry': {'location': {'lat': 12, 'lng': 23}}}]}
        mapbox_obj = {'features': [{'place_type': [{'types': []}], 'geometry': {'coordinates': [23, 12]}}]}

        httpretty.register_uri(httpretty.GET, google_url, body=json.dumps(google_obj))
        httpretty.register_uri(httpretty.GET, mapbox_url, body=json.dumps(mapbox_obj))

        parameters = {
            '_vault_id': VAULT_ID,
            '_carrier_wallet_id': CARRIER_WALLET_ID,
            '_shipper_wallet_id': SHIPPER_WALLET_ID,
            '_storage_credentials_id': STORAGE_CRED_ID,
            '_async_hash': 'txHash',
            '_ship_from_location_city': LOCATION_CITY,
            '_ship_from_location_state': LOCATION_STATE,
            '_ship_from_location_name': LOCATION_NAME,
            '_ship_to_location_name': LOCATION_NAME_2,
            '_ship_to_location_city': LOCATION_CITY,
            '_ship_to_location_state': LOCATION_STATE,
        }

        one_location, content_type = create_form_content({'ship_from_location.name': LOCATION_NAME,
                                                          'ship_from_location.city': LOCATION_CITY,
                                                          'ship_from_location.state': LOCATION_STATE
                                                          })

        two_locations, content_type = create_form_content({'ship_from_location.name': LOCATION_NAME,
                                                           'ship_from_location.city': LOCATION_CITY,
                                                           'ship_from_location.state': LOCATION_STATE,
                                                           'ship_to_location.name': LOCATION_NAME_2,
                                                           'ship_to_location.city': LOCATION_CITY,
                                                           'ship_to_location.state': LOCATION_STATE
                                                           })

        # Mock RPC calls
        mock_shipment_rpc_client = Load110RPCClient

        mock_shipment_rpc_client.add_shipment_data = mock.Mock(return_value={"hash": "txHash"})
        mock_shipment_rpc_client.sign_transaction = mock.Mock(return_value=({}, 'txHash'))
        mock_shipment_rpc_client.update_vault_hash_transaction = mock.Mock(return_value=({}))
        mock_shipment_rpc_client.update_vault_hash_transaction.__qualname__ = 'ShipmentRPCClient.set_vault_hash_tx'
        mock_shipment_rpc_client.send_transaction = mock.Mock(return_value={
            "blockHash": "0xccb595947a121e37df8bf689c3f88c6d9c7fb56070c9afda38551540f9e231f7",
            "blockNumber": 15,
            "contractAddress": None,
            "cumulativeGasUsed": 138090,
            "from": "0x13b1eebb31a1aa2ecaa2ad9e7455df2f717f2143",
            "gasUsed": 138090,
            "logs": [],
            "logsBloom": "0x0000000000",
            "status": True,
            "to": "0x25ff5dc79a7c4e34254ff0f4a19d69e491201dd3",
            "transactionHash": parameters['_async_hash'],
            "transactionIndex": 0
        })

        # Authenticated request should succeed using mapbox (if exists)
        self.set_user(self.user_1)

        response = self.client.patch(url, one_location, content_type=content_type)
        response_data = response.json()['data']
        response_included = response.json()['included']
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        self.assertEqual(response_data['attributes']['carrier_wallet_id'], parameters['_carrier_wallet_id'])
        self.assertEqual(response_data['attributes']['shipper_wallet_id'], parameters['_shipper_wallet_id'])
        self.assertEqual(response_data['attributes']['storage_credentials_id'],
                         parameters['_storage_credentials_id'])
        self.assertEqual(response_data['attributes']['vault_id'], parameters['_vault_id'])
        self.assertIsNotNone(response_data['meta']['async_job_id'])

        self.assertIsNotNone(response_data['relationships']['ship_from_location']['data'])
        self.assertEqual(len(response_included), 2)
        ship_from_location = Location.objects.get(id=response_data['relationships']['ship_from_location']['data']['id'])
        self.assertEqual(ship_from_location.city, parameters['_ship_from_location_city'])
        self.assertEqual(ship_from_location.state, parameters['_ship_from_location_state'])
        self.assertEqual(ship_from_location.name, parameters['_ship_from_location_name'])
        self.assertEqual(ship_from_location.geometry.coords, (23.0, 12.0))

        # Authenticated request should succeed using mapbox in creating two locations (if exists)
        self.set_user(self.user_1)
        response = self.client.patch(url, two_locations, content_type=content_type)
        response_data = response.json()['data']
        response_included = response.json()['included']
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        self.assertEqual(response_data['attributes']['carrier_wallet_id'], parameters['_carrier_wallet_id'])
        self.assertEqual(response_data['attributes']['shipper_wallet_id'], parameters['_shipper_wallet_id'])
        self.assertEqual(response_data['attributes']['storage_credentials_id'],
                         parameters['_storage_credentials_id'])
        self.assertEqual(response_data['attributes']['vault_id'], parameters['_vault_id'])
        self.assertIsNotNone(response_data['meta']['async_job_id'])

        self.assertIsNotNone(response_data['relationships']['ship_from_location']['data'])
        ship_from_location = Location.objects.get(id=response_data['relationships']['ship_from_location']['data']['id'])
        self.assertEqual(ship_from_location.city, parameters['_ship_from_location_city'])
        self.assertEqual(ship_from_location.state, parameters['_ship_from_location_state'])
        self.assertEqual(ship_from_location.name, parameters['_ship_from_location_name'])
        self.assertEqual(ship_from_location.geometry.coords, (23.0, 12.0))

        self.assertIsNotNone(response_data['relationships']['ship_to_location']['data'])
        self.assertEqual(len(response_included), 3)
        ship_to_location = Location.objects.get(id=response_data['relationships']['ship_to_location']['data']['id'])
        self.assertEqual(ship_to_location.city, parameters['_ship_to_location_city'])
        self.assertEqual(ship_to_location.state, parameters['_ship_to_location_state'])
        self.assertEqual(ship_to_location.name, parameters['_ship_to_location_name'])
        self.assertEqual(ship_to_location.geometry.coords, (23.0, 12.0))

        # Authenticated request should succeed using google
        mapbox_access_token = None
        self.set_user(self.user_1)
        url = reverse('shipment-detail', kwargs={'version': 'v1', 'pk': self.shipments[1].id})

        response = self.client.patch(url, one_location, content_type=content_type)
        response_data = response.json()['data']
        response_included = response.json()['included']
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        self.assertEqual(response_data['attributes']['carrier_wallet_id'], parameters['_carrier_wallet_id'])
        self.assertEqual(response_data['attributes']['shipper_wallet_id'], parameters['_shipper_wallet_id'])
        self.assertEqual(response_data['attributes']['storage_credentials_id'],
                         parameters['_storage_credentials_id'])
        self.assertEqual(response_data['attributes']['vault_id'], parameters['_vault_id'])
        self.assertIsNotNone(response_data['meta']['async_job_id'])

        self.assertIsNotNone(response_data['relationships']['ship_from_location']['data'])
        self.assertEqual(len(response_included), 2)
        ship_from_location = Location.objects.get(id=response_data['relationships']['ship_from_location']['data']['id'])
        self.assertEqual(ship_from_location.city, parameters['_ship_from_location_city'])
        self.assertEqual(ship_from_location.state, parameters['_ship_from_location_state'])
        self.assertEqual(ship_from_location.name, parameters['_ship_from_location_name'])
        self.assertEqual(ship_from_location.geometry.coords, (23.0, 12.0))

        # Authenticated request should succeed using google in creating two locations
        self.set_user(self.user_1)

        response = self.client.patch(url, two_locations, content_type=content_type)
        response_data = response.json()['data']
        response_included = response.json()['included']
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        self.assertEqual(response_data['attributes']['carrier_wallet_id'], parameters['_carrier_wallet_id'])
        self.assertEqual(response_data['attributes']['shipper_wallet_id'], parameters['_shipper_wallet_id'])
        self.assertEqual(response_data['attributes']['storage_credentials_id'],
                         parameters['_storage_credentials_id'])
        self.assertEqual(response_data['attributes']['vault_id'], parameters['_vault_id'])
        self.assertIsNotNone(response_data['meta']['async_job_id'])

        self.assertIsNotNone(response_data['relationships']['ship_from_location']['data'])
        ship_from_location = Location.objects.get(id=response_data['relationships']['ship_from_location']['data']['id'])
        self.assertEqual(ship_from_location.city, parameters['_ship_from_location_city'])
        self.assertEqual(ship_from_location.state, parameters['_ship_from_location_state'])
        self.assertEqual(ship_from_location.name, parameters['_ship_from_location_name'])
        self.assertEqual(ship_from_location.geometry.coords, (23.0, 12.0))

        self.assertIsNotNone(response_data['relationships']['ship_to_location']['data'])
        self.assertEqual(len(response_included), 3)
        ship_to_location = Location.objects.get(id=response_data['relationships']['ship_to_location']['data']['id'])
        self.assertEqual(ship_to_location.city, parameters['_ship_to_location_city'])
        self.assertEqual(ship_to_location.state, parameters['_ship_to_location_state'])
        self.assertEqual(ship_to_location.name, parameters['_ship_to_location_name'])
        self.assertEqual(ship_to_location.geometry.coords, (23.0, 12.0))

    @httpretty.activate
    def test_permission_link(self):
        httpretty.register_uri(httpretty.GET,
                               f"{test_settings.PROFILES_URL}/api/v1/wallet/{CARRIER_WALLET_ID}/?is_active",
                               body=json.dumps({'good': 'good'}), status=status.HTTP_404_NOT_FOUND)
        httpretty.register_uri(httpretty.GET,
                               f"{test_settings.PROFILES_URL}/api/v1/wallet/{SHIPPER_WALLET_ID}/?is_active",
                               body=json.dumps({'good': 'good'}), status=status.HTTP_404_NOT_FOUND)

        self.create_shipment()
        url = reverse('shipment-permissions-list', kwargs={'version': 'v1', 'shipment_pk': self.shipments[0].id})
        url_shipment_list = reverse('shipment-list', kwargs={'version': 'v1'})

        today = datetime.now(timezone.utc)
        yesterday = today + timedelta(days=-1)
        tomorrow = today + timedelta(days=1)

        valid_permission_no_exp, content_type = create_form_content({
            'name': 'test'
        })

        valid_permission_past_exp, content_type = create_form_content({
            'name': 'test',
            'expiration_date': yesterday.isoformat()
        })

        valid_permission_with_exp, content_type = create_form_content({
            'name': 'test',
            'expiration_date': tomorrow.isoformat()
        })

        shipment_update_info, content_type = create_form_content({
            'carrier_scac': 'test'
        })

        # Unauthenticated request should fail with 403
        response = self.client.post(url, valid_permission_no_exp, content_type=content_type)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        self.set_user(self.user_1)

        # Authenticated request should succeed
        response = self.client.post(url, valid_permission_no_exp, content_type=content_type)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        response_json = response.json()
        self.assertEqual(response_json['data']['attributes']['shipment_id'], self.shipments[0].id)
        self.assertIsNone(response_json['data']['attributes']['expiration_date'])
        valid_permission_id = response_json['data']['id']

        # Authenticated request should succeed
        response = self.client.post(url, valid_permission_past_exp, content_type=content_type)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        response_json = response.json()
        self.assertEqual(response_json['data']['attributes']['shipment_id'], self.shipments[0].id)
        self.assertTrue(datetime.now(timezone.utc) > parser.parse(response_json['data']['attributes']['expiration_date']))
        valid_permission_id_past_exp = response_json['data']['id']

        # Authenticated request should succeed
        response = self.client.post(url, valid_permission_with_exp, content_type=content_type)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        response_json = response.json()
        self.assertEqual(response_json['data']['attributes']['shipment_id'], self.shipments[0].id)
        self.assertTrue(datetime.now(timezone.utc) < parser.parse(response_json['data']['attributes']['expiration_date']))
        valid_permission_id_with_exp = response_json['data']['id']

        # The shipment owner can access permission links related to that shipment
        response = self.client.get(url)
        response_json = response.json()
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response_json['data']), 3)

        # Another user with valid permission should be able to access that shipment only with permission link
        shipment_url = reverse('shipment-detail', kwargs={'version': 'v1', 'pk': self.shipments[0].id})
        other_shipment_url = reverse('shipment-detail', kwargs={'version': 'v1', 'pk': self.shipments[1].id})

        # The primary user with an invalid/expired code should still succeed
        response = self.client.get(f'{shipment_url}?permission_link={valid_permission_id_past_exp}')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        response = self.client.get(shipment_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.set_user(self.user_2)

        # A tier authenticated user(not shipment owner) cannot access
        # the permission link objects of a shipment not owned
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        # An authenticated user without permission link should not have access
        response = self.client.get(shipment_url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        # Shipments with permission links can only be accessible via shipments-detail endpoint
        # not shipments-list response status should be 403
        response = self.client.get(f'{url_shipment_list}?permission_link={valid_permission_id_with_exp}')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        response = self.client.get(f'{shipment_url}?permission_link={valid_permission_id}')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Assert that users cannot update or delete shipments when using a permission link
        response = self.client.patch(f'{shipment_url}?permission_link={valid_permission_id}',
                                     shipment_update_info, content_type=content_type)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        # Assert that users cannot update or delete shipments when using a permission link
        response = self.client.delete(f'{shipment_url}?permission_link={valid_permission_id}')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        # Assert that users cannot access shipment with expired date but can before expiration date
        response = self.client.get(f'{shipment_url}?permission_link={valid_permission_id_past_exp}')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        # Assert that users cannot access shipment with expired date but can before expiration date
        response = self.client.get(f'{shipment_url}?permission_link={valid_permission_id_with_exp}')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Can only access shipment with permission link associated
        response = self.client.get(f'{other_shipment_url}?permission_link={valid_permission_id}')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        # An invalid code should result in a 403
        response = self.client.get(f'{shipment_url}?permission_link={self.shipments[0].id}')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        # Assert that users with empty permission link cannot access shipment
        response = self.client.get(f'{shipment_url}?permission_link=')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        # Assert that a tier user with valid permission cannot modify a shipment
        response = self.client.patch(f'{shipment_url}?permission_link={valid_permission_id_with_exp}',
                                     shipment_update_info, content_type=content_type)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        # Cannot make a permission link to a shipment not owned
        response = self.client.post(url, valid_permission_with_exp, content_type=content_type)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        # Assert owner can delete their permission link
        self.set_user(self.user_1)
        response = self.client.delete(f'{url}{valid_permission_id}/', valid_permission_with_exp,
                                      content_type=content_type)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(PermissionLink.objects.all().count(), 2)

        # Assert that a non authenticated user can view the shipment
        self.set_user(None)
        response = self.client.get(f'{shipment_url}?permission_link={valid_permission_id_with_exp}')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Assert that an anonymous user with valid permission cannot modified a shipment
        response = self.client.patch(f'{shipment_url}?permission_link={valid_permission_id_with_exp}',
                                     shipment_update_info, content_type=content_type)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        # An anonymous user cannot access a shipment's permission links
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        # An anonymous user cannot access the shipment-list with a valid permission link
        response = self.client.get(f'{url_shipment_list}?permission_link={valid_permission_id_with_exp}')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class TrackingDataAPITests(APITestCase):
    def setUp(self):
        self.client = APIClient()

        self.user_1 = passive_credentials_auth(get_jwt(username='user1@shipchain.io', sub=OWNER_ID))

    def set_user(self, user, token=None):
        self.client.force_authenticate(user=user, token=token)

    def create_shipment(self):
        self.shipments = []
        self.shipments.append(Shipment.objects.create(vault_id=VAULT_ID,
                                                      carrier_wallet_id=CARRIER_WALLET_ID,
                                                      shipper_wallet_id=SHIPPER_WALLET_ID,
                                                      storage_credentials_id=STORAGE_CRED_ID,
                                                      owner_id=self.user_1.id))

    def create_tracking_data(self):
        self.create_shipment()
        self.tracking_data = []
        self.tracking_data.append(TrackingData.objects.create(latitude=-81.04825300,
                                                              longitude=34.628643,
                                                              altitude=335,
                                                              source='gps',
                                                              speed=35,
                                                              shipment=self.shipments[0],
                                                              uncertainty=10,
                                                              version='1.0.0',
                                                              device=Device.objects.create(certificate_id='My-Custom-Device'),
                                                              timestamp="2018-09-18T14:56:23.563847+00:00"))

    @mock_iot
    def test_set_device_id(self):
        from apps.rpc_client import requests
        from tests.utils import mocked_rpc_response

        self.create_tracking_data()
        self.assertEqual(TrackingData.objects.all().count(), 1)

        device_id = 'adfc1e4c-7e61-4aee-b6f5-4d8b95a7ec75'

        # Create device 'thing'
        iot = boto3.client('iot', region_name='us-east-1')
        iot.create_thing(
            thingName=device_id
        )

        # Load device cert into AWS
        with open('tests/data/cert.pem', 'r') as cert_file:
            cert_pem = cert_file.read()
        cert_response = iot.register_certificate(
            certificatePem=cert_pem,
            status='ACTIVE'
        )
        certificate_id = cert_response['certificateId']

        # Set device for Shipment
        with mock.patch.object(requests, 'post') as mock_method:
            mock_method.return_value = mocked_rpc_response({
                "jsonrpc": "2.0",
                "result": {
                    "success": True,
                    "vault_id": "TEST_VAULT_ID"
                }
            })
            self.create_shipment()
            self.shipments[0].device = Device.objects.create(
                id=device_id,
                certificate_id=certificate_id
            )

            # Attache shipment to tracking data object
            self.tracking_data[0].shipment = self.shipments[0]

            # Check float data type in db
            self.assertTrue(isinstance(self.tracking_data[0].latitude, float))
            self.assertEqual(self.tracking_data[0].altitude, 335)


class FakeBotoAWSRequestsAuth(BotoAWSRequestsAuth):
    def __init__(self, *args, **kwargs):
        pass

    def get_aws_request_headers_handler(self, r):
        return {}


@mock.patch('apps.iot_client.BotoAWSRequestsAuth', FakeBotoAWSRequestsAuth)
class ShipmentWithIoTAPITests(APITestCase):

    def setUp(self):
        self.client = APIClient()

        self.token = get_jwt(username='user1@shipchain.io')
        self.user_1 = passive_credentials_auth(self.token)

    def set_user(self, user, token=None):
        self.client.force_authenticate(user=user, token=token)

    def create_shipment(self):
        url = reverse('shipment-list', kwargs={'version': 'v1'})

        post_data = {
            'device_id': DEVICE_ID,
            'vault_id': VAULT_ID,
            'carrier_wallet_id': CARRIER_WALLET_ID,
            'shipper_wallet_id': SHIPPER_WALLET_ID,
            'storage_credentials_id': STORAGE_CRED_ID,
        }

        with mock.patch('apps.shipments.models.Device.get_or_create_with_permission') as mock_device, \
                mock.patch('apps.shipments.serializers.ShipmentCreateSerializer.validate_shipper_wallet_id') as mock_wallet_validation, \
                mock.patch('apps.shipments.serializers.ShipmentCreateSerializer.validate_storage_credentials_id') as mock_storage_validation:
            mock_device.return_value = Device.objects.get_or_create(id=DEVICE_ID, defaults={'certificate_id': CERTIFICATE_ID})[0]
            mock_wallet_validation.return_value = SHIPPER_WALLET_ID
            mock_storage_validation.return_value = STORAGE_CRED_ID
            response = self.client.post(url, post_data, format='json')
            mock_device.assert_called()
            mock_wallet_validation.assert_called()
            mock_storage_validation.assert_called()

        return response

    def set_device_id(self, shipment_id, device_id, certificate_id):
        url = reverse('shipment-detail', kwargs={'version': 'v1', 'pk': shipment_id})

        with mock.patch('apps.shipments.models.Device.get_or_create_with_permission') as mock_device:
            if device_id:
                mock_device.return_value = Device.objects.get_or_create(id=device_id, defaults={'certificate_id': certificate_id})[0]

            response = self.client.patch(url, {'device_id': device_id}, format='json')

            if device_id:
                mock_device.assert_called()

            else:
                mock_device.assert_not_called()

        return response

    def set_device_id_form_data(self, shipment_id, device_id, certificate_id):
        url = reverse('shipment-detail', kwargs={'version': 'v1', 'pk': shipment_id})

        with mock.patch('apps.shipments.models.Device.get_or_create_with_permission') as mock_device:
            if device_id:
                mock_device.return_value = Device.objects.get_or_create(id=device_id, defaults={'certificate_id': certificate_id})[0]

            device, content_type = create_form_content({'device_id': device_id})

            response = self.client.patch(url, device, content_type='multipart/form-data; boundary=BoUnDaRyStRiNg')

        return response

    @mock_iot
    def test_shipment_set_shadow(self):
        self.set_user(self.user_1, self.token)

        iot = boto3.client('iot', region_name='us-east-1')
        iot.create_thing(
            thingName=DEVICE_ID
        )
        device_2_id = DEVICE_ID[:-1] + '0'
        device_2_cert_id = CERTIFICATE_ID[:-1] + '0'
        iot.create_thing(
            thingName=device_2_id
        )

        with mock.patch('apps.iot_client.requests.Session.put') as mocked:
            mocked_call_count = 0
            mocked.return_value = mocked_rpc_response({'data': {
                'shipmentId': 'dunno yet'
            }})

            # Test Shipment create with Device ID updates shadow
            response = self.create_shipment()
            assert response.status_code == status.HTTP_202_ACCEPTED
            shipment = response.json()['data']

            mocked_call_count += 1
            assert mocked.call_count == mocked_call_count
            mocked.return_value = mocked_rpc_response({'data': {
                'shipmentId': shipment['id']
            }})

            # Test Shipment update with Device ID updates shadow
            response = self.set_device_id(shipment['id'], device_2_id, device_2_cert_id)
            assert response.status_code == status.HTTP_202_ACCEPTED
            mocked_call_count += 2  # Expect the old device to have its shipmentId cleared, and the new one has its set
            assert mocked.call_count == mocked_call_count

            # Test ShipmentComplete event clears Device shadow shipment
            shipment_obj = Shipment.objects.filter(id=shipment['id']).first()
            Shipment.objects.filter(id=shipment['id']).update(contract_version='1.1.0')
            tx_hash = "0x398bb373a52c1d6533820b17d3938e7c19a6a6cf0c965b9923a5b65d34bf7d29"
            eth_action = EthAction.objects.create(transaction_hash=tx_hash, async_job_id=shipment_obj.asyncjob_set.first().id)
            eth_action.ethlistener_set.create(listener=shipment_obj)
            url = reverse('event-list', kwargs={'version': 'v1'})
            data = {
                "address": "0x25Ff5dc79A7c4e34254ff0f4a19d69E491201DD3",
                "blockNumber": 3,
                "transactionHash": tx_hash,
                "transactionIndex": 0,
                "blockHash": "0x62469a8d113b27180c139d88a25f0348bb4939600011d33382b98e10842c85d9",
                "logIndex": 0,
                "removed": False,
                "id": "log_25652065",
                "returnValues": {
                    "0": "0xFCaf25bF38E7C86612a25ff18CB8e09aB07c9885",
                    "shipTokenContractAddress": "0xFCaf25bF38E7C86612a25ff18CB8e09aB07c9885"
                },
                "event": "ShipmentComplete",
                "signature": "0xbbbf32f08c8c0621e580dcf0a8e0024525ec357db61bb4faa1a639d4f958a824",
                "raw": {
                    "data": "0x000000000000000000000000fcaf25bf38e7c86612a25ff18cb8e09ab07c9885",
                    "topics": [
                        "0xbbbf32f08c8c0621e580dcf0a8e0024525ec357db61bb4faa1a639d4f958a824"
                    ]
                }
            }
            response = self.client.post(url, data, format='json', X_NGINX_SOURCE='internal',
                                        X_SSL_CLIENT_VERIFY='SUCCESS', X_SSL_CLIENT_DN='/CN=engine.test-internal')
            # Failing at shipment_post_save after device_id is updated
            assert response.status_code == status.HTTP_204_NO_CONTENT
            mocked_call_count += 1
            assert mocked.call_count == mocked_call_count

            # Reset initial DEVICE_ID
            response = self.set_device_id(shipment['id'], DEVICE_ID, CERTIFICATE_ID)
            assert response.status_code == status.HTTP_202_ACCEPTED
            mocked_call_count += 1
            assert mocked.call_count == mocked_call_count

            # Create second shipment, (will fail since the device is already in use)
            response = self.create_shipment()
            assert response.status_code == status.HTTP_400_BAD_REQUEST
            assert mocked.call_count == mocked_call_count

            # Removing device should fail if there is no delivery_act on the shipment
            response = self.set_device_id(shipment['id'], None, None)
            assert response.status_code == status.HTTP_400_BAD_REQUEST
            assert mocked.call_count == mocked_call_count

            # Devices can be reused after deliveries are complete and should be removed from old shipment
            shipment_obj.refresh_from_db()
            shipment_obj.delivery_act = datetime.now()
            shipment_obj.save()
            shipment_obj.refresh_from_db()

            self.assertIsNone(shipment_obj.device)
            response = self.create_shipment()
            assert response.status_code == status.HTTP_202_ACCEPTED
            mocked_call_count += 4
            assert mocked.call_count == mocked_call_count

            response_json = response.json()
            shipment = Shipment.objects.get(pk=response_json['data']['id'])

            # Device ID updates for Shipments should fail if the device is already in use
            response = self.set_device_id(shipment.id, DEVICE_ID, CERTIFICATE_ID)
            assert response.status_code == status.HTTP_400_BAD_REQUEST

            # Test Shipment null Device ID updates shadow
            shipment.delivery_act = datetime.now()
            shipment.save()

            response = self.set_device_id(shipment.id, None, None)
            shipment.refresh_from_db()
            assert response.status_code == status.HTTP_202_ACCEPTED
            mocked_call_count += 1
            assert mocked.call_count == mocked_call_count

            response = self.create_shipment()
            assert response.status_code == status.HTTP_202_ACCEPTED
            mocked_call_count += 1
            assert mocked.call_count == mocked_call_count

            response_json = response.json()
            shipment = Shipment.objects.get(pk=response_json['data']['id'])

            shipment.delivery_act = datetime.now()
            shipment.save()
            print('Before test: ', mocked.call_count)

            # Setting device_id with form data should also succeed
            response = self.set_device_id_form_data(shipment.id, '', None)
            print(response.content)
            assert response.status_code == status.HTTP_202_ACCEPTED
            print('After test: ', mocked.call_count)
            mocked_call_count += 1
            assert mocked.call_count == mocked_call_count
