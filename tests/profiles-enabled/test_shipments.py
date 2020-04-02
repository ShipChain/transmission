import json
from datetime import datetime, timezone, timedelta
from unittest import mock

import boto3
import copy
import geocoder
import httpretty
import re
import requests
from aws_requests_auth.boto_utils import BotoAWSRequestsAuth
from dateutil import parser
from django.conf import settings as test_settings
from django.core import mail
from freezegun import freeze_time
from jose import jws
from moto import mock_iot
from rest_framework import status
from rest_framework.reverse import reverse
from rest_framework.test import APITestCase, force_authenticate, APIClient
from shipchain_common.test_utils import replace_variables_in_string, create_form_content, mocked_rpc_response, \
    get_jwt, GeoCoderResponse

from apps.authentication import passive_credentials_auth
from apps.eth.models import EthAction
from apps.shipments.models import Shipment, Location, Device, TrackingData, PermissionLink, random_id
from apps.shipments.rpc import Load110RPCClient

boto3.setup_default_session()  # https://github.com/spulec/moto/issues/1926

VAULT_ID = 'b715a8ff-9299-4c87-96de-a4b0a4a54509'
CARRIER_WALLET_ID = '3716ff65-3d03-4b65-9fd5-43d15380cff9'
SHIPPER_WALLET_ID = '48381c16-432b-493f-9f8b-54e88a84ec0a'
MODERATOR_WALLET_ID = '71baef8e-7067-493a-b533-51ed84c0124a'
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
LOCATION_POSTAL_CODE = '29600'
NEXT_TOKEN = 'DummyIotNextToken'
SHIPMENT_ID = '332dc6c8-b89e-449e-a802-0bfe760f83ff'
VAULT_HASH = '0xe9f28cb025350ef700158eed9a5b617a4f4185b31de06864fd02d67c839df583'

mapbox_url = re.compile(r'https://api.mapbox.com/geocoding/v5/mapbox.places/[\w$\-@&+%,]+.json')
google_url = f'https://maps.googleapis.com/maps/api/geocode/json'


class ShipmentAPITests(APITestCase):
    def setUp(self):
        self.client = APIClient()

        self.token = get_jwt(username='user1@shipchain.io', sub=OWNER_ID, organization_id=ORGANIZATION_ID)
        self.token2 = get_jwt(username='user2@shipchain.io', sub=OWNER_ID_2)
        self.token3 = get_jwt(username='user3@shipchain.io', sub=OWNER_ID_3, organization_id=ORGANIZATION_ID)
        self.hashed_token = get_jwt(username='user1@shipchain.io', sub=OWNER_ID, organization_id=ORGANIZATION_ID,
                                    background_data_hash_interval=25, manual_update_hash_interval=30)
        self.gtx_token = get_jwt(username='user1@shipchain.io', sub=OWNER_ID, organization_id=ORGANIZATION_ID,
                                 features={'gtx': ['shipment_use']})

        self.user_1 = passive_credentials_auth(self.token)
        self.user_2 = passive_credentials_auth(self.token2)
        self.user_3 = passive_credentials_auth(self.token3)
        self.gtx_user = passive_credentials_auth(self.gtx_token)

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

        # Filtering for shipment's with fields should return only those with it
        response = self.client.get(f'{url}?has_ship_to_location=True')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        response_data = response.json()
        self.assertEqual(response_data['data'][0]['id'], self.shipments[1].id)

        setattr(self.shipments[1], 'customer_fields', {'string': 'string'})
        self.shipments[1].save()

        # Filtering for shipment's with customer fields should return only those with it
        response = self.client.get(f'{url}?customer_fields__has_key=string')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        response_data = response.json()
        self.assertEqual(response_data['data'][0]['id'], self.shipments[1].id)

        # Filtering off a shipment state should fail if invalid state supplied
        response = self.client.get(f'{url}?state=string')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        self.shipments[1].pick_up()
        self.shipments[1].save()

        response = self.client.get(f'{url}?state=IN_TRANSIT')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        response_data = response.json()
        self.assertEqual(response_data['data'][0]['id'], self.shipments[1].id)

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

    def test_search(self):
        """
        Test searching for objects
        """
        self.create_shipment()

        # Unauthenticated request should fail with 403
        url = reverse('shipment-list', kwargs={'version': 'v1'})

        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        # Authenticated request should succeed
        self.set_user(self.user_1)

        # Searching for data that no shipment has should return none
        response = self.client.get(f'{url}?search=Location Name')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        response_data = response.json()
        self.assertEqual(len(response_data['data']), 0)

        setattr(self.shipments[1], 'ship_from_location', Location.objects.create(name="locat"))
        self.shipments[1].save()

        # Searching for location data should work
        response = self.client.get(f'{url}?search=locat')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        response_data = response.json()
        self.assertEqual(len(response_data['data']), 1)
        self.assertEqual(response_data['data'][0]['id'], self.shipments[1].id)

        setattr(self.shipments[0], 'shippers_reference', "Shipper Reference")
        self.shipments[0].save()

        # Searching for shippers_reference should work
        response = self.client.get(f'{url}?search=Shipper Reference')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        response_data = response.json()
        self.assertEqual(len(response_data['data']), 1)
        self.assertEqual(response_data['data'][0]['id'], self.shipments[0].id)

        cf_time = datetime.now()

        setattr(self.shipments[0], 'customer_fields', {'number': 1, 'boolean': True, 'array': ['A', 'B', 'C']})
        self.shipments[0].save()

        setattr(self.shipments[1], 'customer_fields', {'string': 'string', 'datetime': str(cf_time), 'decimal': 12.5})
        self.shipments[1].save()

        # Searching for shipment's with customer fields should work regardless of type
        response = self.client.get(f'{url}?customer_fields__number=1')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        response_data = response.json()
        self.assertEqual(len(response_data['data']), 1)
        self.assertEqual(response_data['data'][0]['id'], self.shipments[0].id)

        response = self.client.get(f'{url}?customer_fields__string=string')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        response_data = response.json()
        self.assertEqual(len(response_data['data']), 1)
        self.assertEqual(response_data['data'][0]['id'], self.shipments[1].id)

        response = self.client.get(f'{url}?customer_fields__boolean=true')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        response_data = response.json()
        self.assertEqual(len(response_data['data']), 1)
        self.assertEqual(response_data['data'][0]['id'], self.shipments[0].id)

        response = self.client.get(f'{url}?customer_fields__datetime={cf_time}')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        response_data = response.json()
        self.assertEqual(len(response_data['data']), 1)
        self.assertEqual(response_data['data'][0]['id'], self.shipments[1].id)

        response = self.client.get(f'{url}?customer_fields__array=["A", "B", "C"]')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        response_data = response.json()
        self.assertEqual(len(response_data['data']), 1)
        self.assertEqual(response_data['data'][0]['id'], self.shipments[0].id)

        response = self.client.get(f'{url}?customer_fields__decimal=12.5')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        response_data = response.json()
        self.assertEqual(len(response_data['data']), 1)
        self.assertEqual(response_data['data'][0]['id'], self.shipments[1].id)

    def test_carrier_shipment_access(self):
        """
        Ensure that the owner of a shipment's carrier wallet is able to access and update shipment objects.
        """

        with mock.patch.object(requests.Session, 'post') as mock_method:
            mock_method.return_value = mocked_rpc_response({
                "jsonrpc": "2.0",
                "result": {
                    "success": True,
                    "vault_id": "TEST_VAULT_ID",
                    "vault_uri": "engine://test_url",
                    "vault_signed": {'hash': "TEST_VAULT_SIGNATURE"}
                }
            })
            self.create_shipment()

            url = reverse('shipment-detail', kwargs={'version': 'v1', 'pk': self.shipments[0].id})

            with mock.patch('apps.permissions.IsShipperMixin.has_shipper_permission') as mock_carrier, \
                mock.patch('apps.permissions.IsCarrierMixin.has_carrier_permission') as mock_shipper, \
                mock.patch('apps.shipments.serializers.ShipmentCreateSerializer.validate_shipper_wallet_id') \
                    as mock_wallet_validation, \
                mock.patch('apps.shipments.serializers.ShipmentCreateSerializer.validate_storage_credentials_id') \
                    as mock_storage_validation:

                mock_carrier.return_value = False
                mock_shipper.return_value = False

                mock_wallet_validation.return_value = SHIPPER_WALLET_ID
                mock_storage_validation.return_value = STORAGE_CRED_ID

                # Unauthenticated request should fail with 403
                response = self.client.get(url)
                self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

                # Authenticated request for shipment owner should succeed
                self.set_user(self.user_1)

                response = self.client.get(url)
                self.assertEqual(response.status_code, status.HTTP_200_OK)

                # User_2 is shipment's carrier
                mock_carrier.return_value = True

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
                    "vault_id": "TEST_VAULT_ID",
                    "vault_uri": "engine://test_url",
                    "vault_signed": {'hash': "TEST_VAULT_SIGNATURE"}
                }
            })
            self.create_shipment()
            self.shipments[0].device = Device.objects.create(
                id=device_id,
                certificate_id=certificate_id
            )

            tracking_get_url = reverse('shipment-tracking', kwargs={'version': 'v1', 'pk': self.shipments[0].id})

            mock_method.return_value = mocked_rpc_response({
                "jsonrpc": "2.0",
                "result": {
                    "success": True,
                    "vault_signed": {'hash': "TEST_VAULT_SIGNATURE"}
                }
            })
            self.shipments[0].save()

            # A shipment shipper, carrier, moderator should succeed sharing a shipment via email
            with mock.patch('apps.permissions.IsShipperMixin.has_shipper_permission') as mock_carrier, \
                    mock.patch('apps.permissions.IsCarrierMixin.has_carrier_permission') as mock_shipper:
                mock_carrier.return_value = False
                mock_shipper.return_value = False

                # Get tracking data
                response = self.client.get(tracking_get_url)

                # Unauthenticated request should fail
                self.assertEqual(response.status_code, 403)

            self.set_user(self.user_1)
            # Authenticated request with no tracking data associated should fail
            response = self.client.get(tracking_get_url)
            response_json = response.json()
            self.assertEqual(response.status_code, 404)
            self.assertTrue("No tracking data found for Shipment" in response_json['errors'][0]['detail'])

            url = reverse('device-tracking', kwargs={'version': 'v1', 'pk': 'adfc1e4c-7e61-4aee-b6f5-4d8b95a7ec75'})

            track_dic = {
                'position': {
                    'latitude': 75.0587610,
                    'longitude': -35.628643,
                    'altitude': 554,
                    'source': 'Gps',
                    'uncertainty': 92,
                    'speed': 34.56
                },
                'version': '1.0.0',
                'device_id': 'adfc1e4c-7e61-4aee-b6f5-4d8b95a7ec75',
                'timestamp': '2018-09-18T15:02:30.563847+00:00'
            }
            with open('tests/data/eckey.pem', 'r') as key_file:
                key_pem = key_file.read()
            signed_data = jws.sign(track_dic, key=key_pem, headers={'kid': certificate_id}, algorithm='ES256')

            # Send tracking update
            response = self.client.post(url, {'payload': signed_data})
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
            response = self.client.post(url, list_payload)
            self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
            self.assertEqual(TrackingData.objects.all().count(), 3)

            # Authenticated request should succeed
            response = self.client.get(tracking_get_url)
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
            response = self.client.post(url, {'payload': signed_data})
            self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
            self.assertEqual(TrackingData.objects.all().count(), 4)

            # Test second tracking data
            response = self.client.get(tracking_get_url)
            self.assertTrue(response.status_code, status.HTTP_200_OK)
            data = json.loads(response.content)['data']
            self.assertEqual(len(data['features']), 4)

            # -------------------- Get tracking data through permission link --------------------#
            valid_permission_link = PermissionLink.objects.create(
                expiration_date=datetime.now(timezone.utc) + timedelta(days=1),
                shipment=self.shipments[0]
            )

            invalid_permission_link = PermissionLink.objects.create(
                expiration_date=datetime.now(timezone.utc) + timedelta(days=-1),
                shipment=self.shipments[0]
            )

            # An anonymous user shouldn't have access to a shipment tracking data
            self.set_user(None)
            response = self.client.get(tracking_get_url)
            self.assertTrue(response.status_code, status.HTTP_403_FORBIDDEN)

            # An anonymous user with an invalid permission link shouldn't have access to the shipment tracking data
            response = self.client.get(f'{tracking_get_url}?permission_link={invalid_permission_link.id}')
            self.assertTrue(response.status_code, status.HTTP_403_FORBIDDEN)

            # An anonymous user with a valid permission link should have access to the shipment tracking data
            response = self.client.get(f'{tracking_get_url}?permission_link={valid_permission_link.id}')
            self.assertTrue(response.status_code, status.HTTP_200_OK)
            data = json.loads(response.content)['data']
            self.assertEqual(len(data['features']), 4)

            self.set_user(self.user_1)

            # We expect the second point data to be the first in LineString
            # since it has been  generated first. See timestamp values
            pos = track_dic_2['position']
            self.assertEqual(data['features'][0]['geometry']['coordinates'], [pos['longitude'], pos['latitude']])

            # Get data as point
            url_as_point = tracking_get_url + '?as_point'
            response = self.client.get(url_as_point)
            self.assertTrue(response.status_code, status.HTTP_200_OK)
            data = json.loads(response.content)['data']
            self.assertTrue(isinstance(data['features'], list))
            self.assertEqual(data['features'][0]['geometry']['type'], 'Point')

            # Certificate ID not in AWS
            signed_data = jws.sign(track_dic, key=key_pem, headers={'kid': 'notarealcertificateid'}, algorithm='ES256')
            response = self.client.post(url, {'payload': signed_data})
            self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

            # Signed by a different key
            with open('tests/data/eckey2.pem', 'r') as key_file:
                bad_key = key_file.read()
            signed_data = jws.sign(track_dic, key=bad_key, headers={'kid': certificate_id}, algorithm='ES256')
            response = self.client.post(url, {'payload': signed_data})
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
            bad_url = reverse('shipment-tracking', kwargs={'version': 'v1', 'pk': bad_device_id})

            signed_data = jws.sign(track_dic, key=bad_key, headers={'kid': bad_cert_id}, algorithm='ES256')
            response = self.client.post(url, {'payload': signed_data})
            self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

            # Posting to a device not associated with a shipment should fail
            response = self.client.post(bad_url, {'payload': signed_data})

            # Invalid JWS
            response = self.client.post(url, {'payload': {'this': 'is not a jws'}})
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
            response = self.client.post(url, {'payload': 'neither.is.this'})
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
            response = self.client.post(url, {'payload': 'or.this'})
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
            response = self.client.post(url, {'payload': 'bm9ybm9ybm9y.aXNpc2lz.dGhpc3RoaXN0aGlz'})
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

            # Certificate not ACTIVE
            iot.update_certificate(certificateId=certificate_id, newStatus='REVOKED')
            signed_data = jws.sign(track_dic, key=key_pem, headers={'kid': certificate_id}, algorithm='ES256')
            response = self.client.post(url, {'payload': signed_data})
            self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
            iot.update_certificate(certificateId=certificate_id, newStatus='ACTIVE')

            # Device not assigned to shipment
            Shipment.objects.filter(id=self.shipments[0].id).update(device_id=None)
            response = self.client.post(url, {'payload': signed_data})
            self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

            # Assert that calls other than GET/POST fail
            response = self.client.put(url, {'payload': signed_data})
            self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

            # Assert that calls other than GET/POST fail
            response = self.client.put(tracking_get_url, {'payload': signed_data})
            self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_shipment_update(self):
        self.create_shipment()
        url = reverse('shipments-detail', kwargs={'version': 'v1', 'pk': self.shipments[0].id})

        successful_delivery_act, content_type = create_form_content({'delivery_act': datetime.now()})
        datetime_aware_delivery_act, content_type = create_form_content({'delivery_act': "2008-09-15T15:53:00+05:00"})
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

    def test_shipment_customer_fields_update(self):
        with mock.patch.object(requests.Session, 'post') as mock_method:
            mock_method.return_value = mocked_rpc_response({
                "jsonrpc": "2.0",
                "result": {
                    "success": True,
                    "vault_id": "TEST_VAULT_ID"
                }
            })
            self.create_shipment()
        url = reverse('shipment-detail', kwargs={'version': 'v1', 'pk': self.shipments[0].id})

        shipment_customer_fields_1 = {
            'customer_fields': {
                'field_1': 'value_1',
                'field_2': 'value_2',
            }
        }

        shipment_customer_fields_2 = {
            'customer_fields': {
                'field_1': 'value_1 updated',
                'field_3': 'value_3'
            }
        }

        self.set_user(self.user_1)

        response = self.client.patch(url, shipment_customer_fields_1)
        self.assertTrue(response.status_code == status.HTTP_202_ACCEPTED)
        customer_fields = response.json()['data']['attributes']['customer_fields']
        self.assertEqual(customer_fields, shipment_customer_fields_1['customer_fields'])

        # An additionally added key to customer_field should be present in the customer_fields
        # and the response should preserve the previously added fields
        response = self.client.patch(url, shipment_customer_fields_2)
        self.assertTrue(response.status_code == status.HTTP_202_ACCEPTED)
        customer_fields = response.json()['data']['attributes']['customer_fields']
        self.assertEqual(customer_fields['field_1'], shipment_customer_fields_2['customer_fields']['field_1'])
        self.assertEqual(customer_fields['field_2'], shipment_customer_fields_1['customer_fields']['field_2'])
        self.assertEqual(customer_fields['field_3'], shipment_customer_fields_2['customer_fields']['field_3'])

    def test_update_shipment_device_certificate(self):
        """
        The shipment's device certificate has been updated but the the old certificate is still attached to the device.
        when we post new tracking data, we should be able to track and retrieve the new certificate in aws IoT and
        attach it to the device
        """

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

            with mock.patch('apps.shipments.iot_client.DeviceAWSIoTClient.update_shadow') as mocked:
                mocked.return_value = mocked_rpc_response({'data': {
                    'shipmentId': self.shipments[0].id
                }})
                self.shipments[0].save()

        url = reverse('device-tracking', kwargs={'version': 'v1', 'pk': 'adfc1e4c-7e61-4aee-b6f5-4d8b95a7ec75'})

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
            response = self.client.post(url, {'payload': signed_data})
            self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
            # The new certificate should be attached to the shipment's device
            device = self.shipments[0].device
            device.refresh_from_db()
            self.assertEqual(device.certificate_id, new_active_certificate)

            # Creating a new shipment with a device for which the certificate has expired and a new one has been issued
            self.shipments[0].device = None
            with mock.patch('apps.shipments.iot_client.DeviceAWSIoTClient.update_shadow') as mocked:
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

                with mock.patch('apps.shipments.iot_client.DeviceAWSIoTClient.update_shadow') as mocked:
                    mocked.return_value = mocked_rpc_response({'data': {
                        'shipmentId': 'dunno yet'
                    }})
                    response = self.client.post(url, post_data)
                self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)

                # The new certificate should be attached to the shipment's device
                device.refresh_from_db()
                self.assertEqual(device.certificate_id, new_active_certificate)
                response_data = response.json()
                included_object = response_data['included']
                self.assertEqual(device.shipment.id, response_data['data']['id'])
                for included in included_object:
                    if included['type'] == 'Device':
                        assert 'certificate_id' not in included['attributes']
                        break

    def get_changed_fields(self, changes_list, field_name):
        return [item[field_name] for item in changes_list]

    @mock_iot
    @mock.patch('apps.shipments.models.shipment.mapbox_access_token', return_value='TEST_ACCESS_KEYS')
    def test_shipment_history(self, mock_mapbox):

        history = Shipment.history.all()
        history.delete()
        self.assertEqual(history.count(), 0)

        device_id = 'adfc1e4c-7e61-4aee-b6f5-4d8b95a7ec75'

        device = Device.objects.create(id=device_id)

        with mock.patch('apps.shipments.serializers.ShipmentCreateSerializer.validate_shipper_wallet_id') as mock_wallet_validation, \
                mock.patch('apps.shipments.serializers.ShipmentCreateSerializer.validate_storage_credentials_id') as mock_storage_validation, \
                mock.patch('apps.shipments.models.Device.get_or_create_with_permission') as mock_get_or_create_with_permission, \
                mock.patch.object(requests.Session, 'post') as mock_rpc, \
                mock.patch('apps.shipments.iot_client.DeviceAWSIoTClient.update_shadow') as mock_shadow:

            mock_wallet_validation.return_value = SHIPPER_WALLET_ID
            mock_storage_validation.return_value = STORAGE_CRED_ID
            mock_get_or_create_with_permission.return_value = device

            mock_shadow.return_value = mocked_rpc_response({'data': {'shipmentId': 'Test'}})

            mock_rpc.return_value = mocked_rpc_response({
                "jsonrpc": "2.0",
                "result": {
                    "success": True,
                    "vault_id": "TEST_VAULT_ID",
                    "vault_uri": "engine://test_url",
                    "vault_signed": {'hash': "TEST_VAULT_SIGNATURE"}
                }
            })

            self.set_user(self.user_1)

            create_shipment_data = {
                'vault_id': VAULT_ID,
                'carrier_wallet_id': CARRIER_WALLET_ID,
                'shipper_wallet_id': SHIPPER_WALLET_ID,
                'storage_credentials_id': STORAGE_CRED_ID
            }

            update_shipment_data = {
                'package_qty': 5,
                'pickup_act': datetime.utcnow()
            }

            url = reverse('shipment-list', kwargs={'version': 'v1'})

            # Every shipment created should have tow historical objects, one for the shipment
            # creation and one for shipment update with engine metadata.
            response = self.client.post(url, create_shipment_data)
            self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
            data = response.json()['data']
            shipment_id = data['id']
            history = Shipment.history.all()
            self.assertEqual(history.count(), 2)

            history_url = reverse('shipment-history-list', kwargs={'version': 'v1', 'shipment_pk': shipment_id})

            # On shipment creation, we should have the newly created values against null values.
            response = self.client.get(history_url)
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            history_data = response.json()['data']
            self.assertEqual(len(history_data), 2)
            old_values = self.get_changed_fields(history_data[1]['fields'], 'old')

            for old in old_values:
                assert old is None

            engine_changes = self.get_changed_fields(history_data[0]['fields'], 'field')
            assert 'vault_uri' in engine_changes
            # On shipment creation, the most recent change is from a background task. Should have a null author.
            self.assertIsNone(history_data[0]['author'])

            # version field shouldn't be in historical changes
            changed_fields = self.get_changed_fields(history_data[1]['fields'], 'field')
            self.assertTrue('version' not in changed_fields)

            url_patch = reverse('shipment-detail', kwargs={'version': 'v1', 'pk': shipment_id})

            # Existing shipment updated with new fields values should have history diff
            response = self.client.patch(url_patch, update_shipment_data)
            self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)

            response = self.client.get(history_url)
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            history_data = response.json()['data']
            fields = history_data[0]['fields']
            self.assertTrue(len(fields) > 0)
            changed_fields = self.get_changed_fields(fields, 'field')
            self.assertTrue('package_qty' in changed_fields)
            self.assertTrue('pickup_act' not in changed_fields)  # pickup_act should not be editable

            # ----------------------- Shipment update with a location field --------------------------#
            # Equivalently valid for any location field
            with mock.patch.object(geocoder, 'mapbox') as mock_geocoder:
                mock_geocoder.return_value = GeoCoderResponse(status=True, point=(53.1, -35.87))

                shipment_creation_with_location, content_type = create_form_content({
                    'vault_id': VAULT_ID,
                    'carrier_wallet_id': CARRIER_WALLET_ID,
                    'shipper_wallet_id': SHIPPER_WALLET_ID,
                    'storage_credentials_id': STORAGE_CRED_ID,
                    'ship_from_location.name': LOCATION_NAME,
                    'ship_from_location.city': LOCATION_CITY,
                    'ship_from_location.state': LOCATION_STATE
                })

                shipment_update_with_location, content_type = create_form_content({
                    'ship_from_location.name': LOCATION_NAME,
                    'ship_from_location.city': LOCATION_CITY,
                    'ship_from_location.state': LOCATION_STATE,
                })

                # Creating a shipment with a location should be reflected in the initial diff history
                response = self.client.post(url, shipment_creation_with_location, content_type=content_type)
                self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
                shipment2 = response.json()
                # The created shipment has the geometry field populated
                self.assertTrue(isinstance(shipment2['included'][1]['attributes']['geometry'], dict))
                shipment2_id = shipment2['data']['id']

                shipment2_history_url = reverse('shipment-history-list', kwargs={'version': 'v1', 'shipment_pk': shipment2_id})

                response = self.client.get(shipment2_history_url)
                self.assertEqual(response.status_code, status.HTTP_200_OK)
                history_data = response.json()['data'][1]
                changed_fields = self.get_changed_fields(history_data['fields'], 'field')
                self.assertTrue('ship_from_location' in changed_fields)
                self.assertTrue('ship_from_location' in history_data['relationships'].keys())
                # The shipment location geometry field should not be part of the historical changes
                location_fields = self.get_changed_fields(history_data['relationships']['ship_from_location'], 'field')
                self.assertTrue('geometry' not in location_fields)

                # Updating a shipment with a location object, should be reflected in both fields
                # and relationships fields in response data
                response = self.client.patch(url_patch, shipment_update_with_location, content_type=content_type)
                self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)

                response = self.client.get(history_url)
                self.assertEqual(response.status_code, status.HTTP_200_OK)
                history_data = response.json()['data'][0]
                changed_fields = self.get_changed_fields(history_data['fields'], 'field')
                self.assertTrue('ship_from_location' in changed_fields)
                self.assertTrue('ship_from_location' in history_data['relationships'].keys())

                shipment_update_with_location, content_type = create_form_content({
                    'ship_from_location.country': LOCATION_COUNTRY,
                    'ship_from_location.postal_code': LOCATION_POSTAL_CODE,
                    'ship_from_location.phone_number': LOCATION_NUMBER
                })

                # Updating an existing shipment location should yield to a diff location
                # in the response's relationships field
                response = self.client.patch(url_patch, shipment_update_with_location, content_type=content_type)
                self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)

                response = self.client.get(history_url)
                self.assertEqual(response.status_code, status.HTTP_200_OK)
                history_data = response.json()['data']
                ship_from_location_changes = history_data[0]['relationships'].get('ship_from_location', None)
                self.assertTrue(bool(ship_from_location_changes))
                ship_from_location_field_changes = self.get_changed_fields(ship_from_location_changes, 'field')
                self.assertTrue('phone_number' in ship_from_location_field_changes)

            # ----------------------- Linking a Document to shipment --------------------------#
            from apps.documents.models import Document

            # A document in upload_status pending shouldn't be present in the shipment diff history
            document = Document.objects.create(name='Test Historical', owner_id=OWNER_ID, shipment_id=shipment_id)

            response = self.client.get(history_url)
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            history_data = response.json()['data']
            history_documents = history_data[0]['relationships'].get('documents')
            self.assertIsNone(history_documents)

            # A document with upload_status complete should be present in the shipment history
            document.upload_status = 1
            document.save()

            response = self.client.get(history_url)
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            history_data = response.json()['data']
            history_documents = history_data[0]['relationships'].get('documents')
            self.assertTrue(history_documents)
            history_document_changes = self.get_changed_fields(history_documents['fields'], 'field')
            self.assertTrue('upload_status' in history_document_changes)

            # Any subsequent document object update should be present in the diff change
            document.description = 'Document updated with some description for example'
            document.save()

            response = self.client.get(history_url)
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            history_data = response.json()['data']
            history_documents = history_data[0]['relationships'].get('documents')
            self.assertTrue(history_documents)
            history_document_changes = self.get_changed_fields(history_documents['fields'], 'field')
            self.assertTrue('description' in history_document_changes)

            # ----------------------- Shipment update by someone other than owner --------------------------#
            with mock.patch('apps.permissions.IsShipperMixin.has_shipper_permission') as mock_shipper_permission:
                mock_shipper_permission.return_value = True

                self.set_user(self.user_2)

                shipment_update_with_device, content_type = create_form_content({
                    'device_id': device_id,
                })

                # User_2 is the shipment's shipper, any changes made by him should be reflected in the diff history
                # and his ID in the 'author' field of the related diff change
                response = self.client.patch(url_patch, shipment_update_with_device, content_type=content_type)
                self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
                # The has_shipper_permission method is called once for accessing the shipment update view
                self.assertEqual(mock_shipper_permission.call_count, 1)

                response = self.client.get(history_url)
                self.assertEqual(response.status_code, status.HTTP_200_OK)
                # has_shipper_permission method is called once just for accessing the shipment history
                self.assertEqual(mock_shipper_permission.call_count, 2)
                history_data = response.json()['data']
                changed_fields = self.get_changed_fields(history_data[0]['fields'], 'field')
                self.assertIn('device', changed_fields)
                self.assertIn('updated_by', changed_fields)
                self.assertNotEqual(history_data[0]['author'], history_data[1]['author'])

            # ------------------------------- customer_fields test ----------------------------------#
            self.set_user(self.user_1)

            shipment_update_customer_fields = {
                'customer_fields': {
                    'custom_field_1': 'value one',
                    'custom_field_2': 'value two'
                }
            }

            response = self.client.patch(url_patch, shipment_update_customer_fields)
            self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
            self.assertEqual(response.json()['data']['attributes']['customer_fields'],
                             shipment_update_customer_fields['customer_fields'])

            response = self.client.get(history_url)
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            history_data = response.json()['data']
            changed_fields = self.get_changed_fields(history_data[0]['fields'], 'field')
            self.assertTrue('customer_fields.custom_field_1' in changed_fields)
            self.assertTrue('customer_fields.custom_field_2' in changed_fields)

            # Ensure that a modified customer_fields is reflected in historical diff changes
            shipment_update_customer_fields['customer_fields']['custom_field_1'] = 'value one modified'

            response = self.client.patch(url_patch, shipment_update_customer_fields)
            self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
            self.assertEqual(response.json()['data']['attributes']['customer_fields'],
                             shipment_update_customer_fields['customer_fields'])

            response = self.client.get(history_url)
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            history_data = response.json()['data']
            changed_fields = self.get_changed_fields(history_data[0]['fields'], 'field')
            self.assertTrue('customer_fields.custom_field_1' in changed_fields)
            self.assertTrue('customer_fields.custom_field_2' not in changed_fields)    # Only custom_field_1 has changed

            # Enum representation test
            shipment_action_url = reverse('shipment-actions', kwargs={'version': 'v1', 'shipment_pk': shipment_id})

            shipment_action = {
                'action_type': 'Pick_up'
            }

            response = self.client.post(shipment_action_url, shipment_action)
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            data = response.json()['data']
            self.assertEqual(data['attributes']['state'], 'IN_TRANSIT')

            response = self.client.get(history_url)
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            history_data = response.json()['data']
            changed_fields = self.get_changed_fields(history_data[0]['fields'], 'field')
            self.assertTrue('state' in changed_fields)
            self.assertTrue('pickup_act' in changed_fields)
            for change in history_data[0]['fields']:
                if change['field'] == 'state':
                    # Enum field value should be in their character representation
                    assert change['new'] == 'IN_TRANSIT'

            # ------------------------------- datetime filtering test -------------------------------#
            self.set_user(self.user_1)
            initial_datetime = datetime.now()
            one_day_later = datetime.now() + timedelta(days=1)
            two_day_later = datetime.now() + timedelta(days=2)
            # We update the shipment 1 day in the future

            with freeze_time(one_day_later.isoformat()) as date_in_future:
                shipment_update_package_qty, content_type = create_form_content({
                    'container_qty': '1',
                })
                response = self.client.patch(url_patch, shipment_update_package_qty, content_type=content_type)
                self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)

                # We set the clock to two days in the future
                date_in_future.move_to(two_day_later)
                shipment_update_package_qty, content_type = create_form_content({
                    'package_qty': '10',
                })
                response = self.client.patch(url_patch, shipment_update_package_qty, content_type=content_type)
                self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)

            # The most recent change should be relative to the attribute 'package_qty'
            response = self.client.get(history_url)
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            history_data = response.json()['data']
            total_num_changes = response.json()['meta']['pagination']['count']
            changed_fields = self.get_changed_fields(history_data[0]['fields'], 'field')
            self.assertIn('package_qty', changed_fields)

            # Test changes less than the provided date time
            filter_url = f'{history_url}?history_date__lte={initial_datetime.isoformat()}'
            response = self.client.get(filter_url)
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            history_data = response.json()['data']
            # The changes here should be less than the total changes.
            self.assertTrue(response.json()['meta']['pagination']['count'] < total_num_changes)
            # package_qty shouldn't be in the most recent changed fields
            changed_fields = self.get_changed_fields(history_data[0]['fields'], 'field')
            self.assertTrue('package_qty' not in changed_fields)

            # Test changes greater than the provided date time
            filter_url = f'{history_url}?history_date__gte={initial_datetime.isoformat()}'
            response = self.client.get(filter_url)
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            history_data = response.json()['data']
            # There should be only two changes here, related to the package_qty and container_qty attributes
            self.assertTrue(len(history_data) == 2)
            # package_qty and container_qty should be the only fields in result
            changed_fields = self.get_changed_fields(history_data[0]['fields'], 'field')
            self.assertTrue('package_qty' in changed_fields)
            changed_fields = self.get_changed_fields(history_data[1]['fields'], 'field')
            self.assertTrue('container_qty' in changed_fields)

            # Combining two days later and the current date, should yield to the container_qty change
            filter_url = f'{history_url}?history_date__lte={one_day_later.isoformat()}' \
                         f'&history_date__gte={datetime.now().isoformat()}'
            response = self.client.get(filter_url)
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            history_data = response.json()['data']
            # There should be only one change here, related to the container_qty attribute
            self.assertTrue(len(history_data) == 1)
            # container_qty should be the only field in result
            changed_fields = self.get_changed_fields(history_data[0]['fields'], 'field')
            self.assertTrue('container_qty' in changed_fields)

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
        mock_shipment_rpc_client.create_shipment_transaction.__qualname__ = 'Load110RPCClient.create_shipment_transaction'
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

        shipment = Shipment.objects.get(id=response_data['id'])
        self.assertEqual(shipment.background_data_hash_interval, test_settings.DEFAULT_BACKGROUND_DATA_HASH_INTERVAL)
        self.assertEqual(shipment.manual_update_hash_interval, test_settings.DEFAULT_MANUAL_UPDATE_HASH_INTERVAL)

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

        httpretty.register_uri(httpretty.GET,
                               f"{test_settings.PROFILES_URL}/api/v1/wallet/{parameters['_shipper_wallet_id']}/",
                               body=json.dumps({'good': 'good'}), status=status.HTTP_200_OK)
        httpretty.register_uri(httpretty.GET,
                               f"{test_settings.PROFILES_URL}/api/v1/storage_credentials/{parameters['_storage_credentials_id']}/",
                               body=json.dumps({'good': 'good'}), status=status.HTTP_200_OK)

        self.user_1 = passive_credentials_auth(self.hashed_token)
        self.set_user(self.user_1, self.hashed_token)
        force_authenticate(response, user=self.user_1, token=self.hashed_token)
        response = self.client.post(url, post_data, content_type='application/vnd.api+json')
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        response_data = response.json()['data']

        shipment = Shipment.objects.get(id=response_data['id'])
        self.assertEqual(shipment.background_data_hash_interval, 25)
        self.assertEqual(shipment.manual_update_hash_interval, 30)

        # A user without `gtx.shipment_use` permission should not be able to set `gtx_required`
        httpretty.register_uri(
            httpretty.GET,
            f"{test_settings.PROFILES_URL}/api/v1/wallet/{parameters['_shipper_wallet_id']}/",
            body=json.dumps({'good': 'good'}), status=status.HTTP_200_OK)
        httpretty.register_uri(
            httpretty.GET,
            f"{test_settings.PROFILES_URL}/api/v1/storage_credentials/{parameters['_storage_credentials_id']}/",
            body=json.dumps({'good': 'good'}), status=status.HTTP_200_OK)

        gtx_post_data = json.loads(post_data)
        gtx_post_data['data']['attributes']['gtx_required'] = True
        gtx_post_data = json.dumps(gtx_post_data)

        response = self.client.post(url, gtx_post_data, content_type='application/vnd.api+json')

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.json()['errors'][0]['detail'],
                         'User does not have access to enable GTX for this shipment')

        # A user with `gtx.shipment_use` permission should be able to set `gtx_required`
        httpretty.register_uri(
            httpretty.GET,
            f"{test_settings.PROFILES_URL}/api/v1/wallet/{parameters['_shipper_wallet_id']}/",
            body=json.dumps({'good': 'good'}), status=status.HTTP_200_OK)
        httpretty.register_uri(
            httpretty.GET,
            f"{test_settings.PROFILES_URL}/api/v1/storage_credentials/{parameters['_storage_credentials_id']}/",
            body=json.dumps({'good': 'good'}), status=status.HTTP_200_OK)

        self.set_user(self.gtx_user, self.gtx_token)
        gtx_post_data = json.loads(post_data)
        gtx_post_data['data']['attributes']['gtx_required'] = True
        gtx_post_data = json.dumps(gtx_post_data)

        response = self.client.post(url, gtx_post_data, content_type='application/vnd.api+json')
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        self.assertEqual(response.json()['data']['attributes']['gtx_required'], True)

        # Cannot set asset_physical_id during shipment creation
        httpretty.register_uri(
            httpretty.GET,
            f"{test_settings.PROFILES_URL}/api/v1/wallet/{parameters['_shipper_wallet_id']}/",
            body=json.dumps({'good': 'good'}), status=status.HTTP_200_OK)
        httpretty.register_uri(
            httpretty.GET,
            f"{test_settings.PROFILES_URL}/api/v1/storage_credentials/{parameters['_storage_credentials_id']}/",
            body=json.dumps({'good': 'good'}), status=status.HTTP_200_OK)

        self.set_user(self.user_1, self.hashed_token)
        asset_post_data = json.loads(post_data)
        asset_post_data['data']['attributes']['asset_physical_id'] = random_id()
        asset_post_data = json.dumps(asset_post_data)

        response = self.client.post(url, asset_post_data, content_type='application/vnd.api+json')
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        response_data = response.json()['data']

        shipment = Shipment.objects.get(id=response_data['id'])
        self.assertIsNone(shipment.asset_physical_id)

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
        mock_shipment_rpc_client.create_shipment_transaction.__qualname__ = 'Load110RPCClient.create_shipment_transaction'
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
        response = self.client.post(url, post_data)

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

        location_bad_contact_email, content_type = create_form_content({
            'carrier_wallet_id': CARRIER_WALLET_ID,
            'shipper_wallet_id': SHIPPER_WALLET_ID,
            'storage_credentials_id': STORAGE_CRED_ID,
            'ship_from_location.name': LOCATION_NAME,
            'ship_from_location.contact_email': 'Nonvalid@email',
        })

        location_contact_email, content_type = create_form_content({
            'carrier_wallet_id': CARRIER_WALLET_ID,
            'shipper_wallet_id': SHIPPER_WALLET_ID,
            'storage_credentials_id': STORAGE_CRED_ID,
            'ship_from_location.name': LOCATION_NAME,
            'ship_from_location.contact_email': 'valid@email.io',
        })

        # Mock RPC calls
        mock_shipment_rpc_client = Load110RPCClient

        mock_shipment_rpc_client.create_vault = mock.Mock(return_value=(parameters['_vault_id'], parameters['_vault_uri']))
        mock_shipment_rpc_client.add_shipment_data = mock.Mock(return_value={'hash': 'txHash'})
        mock_shipment_rpc_client.create_shipment_transaction = mock.Mock(return_value=('version', {}))
        mock_shipment_rpc_client.create_shipment_transaction.__qualname__ = 'Load110RPCClient.create_shipment_transaction'
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

        self.set_user(self.user_1)
        # A shipment creation with a invalid location contact email should fail
        response = self.client.post(url, location_bad_contact_email, content_type=content_type)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        # With a valid location contact email, the request should succeed
        response = self.client.post(url, location_contact_email, content_type=content_type)
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)

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
        shipment = Shipment.objects.create(id=_shipment_id, vault_id=_vault_id, owner_id=self.user_1.id)

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
                          "carriers_scac": "test_scac",
                          "asset_physical_id": "asset_physical_id"
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
        # asset_physical_id should not be in response
        self.assertNotIn('asset_physical_id', response_data['attributes'])

        # Cannot update gtx_required if user does not have permission
        self.set_user(self.user_1, self.hashed_token)
        gtx_post_data = json.loads(post_data)
        gtx_post_data['data']['attributes']['gtx_required'] = True
        gtx_post_data = json.dumps(gtx_post_data)

        response = self.client.patch(url, gtx_post_data, content_type='application/vnd.api+json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.json()['errors'][0]['detail'],
                         'User does not have access to modify GTX for this shipment')

        # Can update gtx_required if user has permission and not yet picked up
        self.set_user(self.gtx_user, self.gtx_token)
        response = self.client.patch(url, gtx_post_data, content_type='application/vnd.api+json')
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        response_data = response.json()['data']
        self.assertTrue(response_data['attributes']['gtx_required'])

        # Cannot update gtx_required if user has permission but state is beyond picked up
        self.shipments[0].pick_up()
        self.shipments[0].save()
        response = self.client.patch(url, gtx_post_data, content_type='application/vnd.api+json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.json()['errors'][0]['detail'],
                         'Cannot modify GTX for a shipment in progress')

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


@mock.patch('shipchain_common.iot.BotoAWSRequestsAuth', FakeBotoAWSRequestsAuth)
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
            response = self.client.post(url, post_data)
            mock_device.assert_called()
            mock_wallet_validation.assert_called()
            mock_storage_validation.assert_called()

        return response

    def set_device_id(self, shipment_id, device_id, certificate_id):
        url = reverse('shipment-detail', kwargs={'version': 'v1', 'pk': shipment_id})

        with mock.patch('apps.shipments.models.Device.get_or_create_with_permission') as mock_device:
            if device_id:
                mock_device.return_value = Device.objects.get_or_create(id=device_id, defaults={'certificate_id': certificate_id})[0]

            response = self.client.patch(url, {'device_id': device_id})

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

        with mock.patch('apps.shipments.iot_client.DeviceAWSIoTClient.update_shadow') as mocked:
            mocked_call_count = mocked.call_count
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
            EthAction.objects.create(transaction_hash=tx_hash, async_job_id=shipment_obj.asyncjob_set.first().id, shipment=shipment_obj)
            url = reverse('event-list', kwargs={'version': 'v1'})
            data = {
                'events': {
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
                },
                'project': 'LOAD'
            }
            response = self.client.post(url, data, X_NGINX_SOURCE='internal',
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

            # Set shipment IN_TRANSIT
            shipment_obj = Shipment.objects.filter(id=shipment_obj.id).first()
            shipment_obj.pick_up()
            shipment_obj.save()
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
            shipment_obj = Shipment.objects.filter(id=shipment_obj.id).first()
            shipment_obj.arrival()
            shipment_obj.save()
            mocked_call_count += 1
            assert mocked.call_count == mocked_call_count
            shipment_obj.drop_off()
            shipment_obj.save()
            mocked_call_count += 1
            assert mocked.call_count == mocked_call_count
            shipment_obj = Shipment.objects.filter(id=shipment_obj.id).first()
            assert shipment_obj.device_id == DEVICE_ID  # Dropoff does not clear shipment anymore
            response = self.create_shipment()
            assert response.status_code == status.HTTP_202_ACCEPTED
            mocked_call_count += 2  # Reassignment should be possible after dropoff (two IoT shadow updates)
            assert mocked.call_count == mocked_call_count
            shipment_obj = Shipment.objects.filter(id=shipment_obj.id).first()
            assert not shipment_obj.device_id

            response_json = response.json()
            shipment = Shipment.objects.get(pk=response_json['data']['id'])
            assert shipment.device_id == DEVICE_ID
            shipment.pick_up()
            shipment.save()
            mocked_call_count += 1
            assert mocked.call_count == mocked_call_count

            # Device ID updates for Shipments should fail if the device is already in use
            response = self.set_device_id(shipment_obj.id, DEVICE_ID, CERTIFICATE_ID)
            assert response.status_code == status.HTTP_400_BAD_REQUEST

            # Test Shipment null Device ID updates shadow
            shipment.arrival()
            shipment.save()
            mocked_call_count += 1
            assert mocked.call_count == mocked_call_count
            shipment.drop_off()
            shipment.save()
            mocked_call_count += 1
            assert mocked.call_count == mocked_call_count

            response = self.set_device_id(shipment.id, None, None)
            shipment.refresh_from_db(fields=('device',))
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

            # Setting device_id with form data should also succeed
            response = self.set_device_id_form_data(shipment.id, '', None)
            assert response.status_code == status.HTTP_202_ACCEPTED
            mocked_call_count += 1
            assert mocked.call_count == mocked_call_count
