from unittest import mock

import boto3
import jwt
import json
from geocoder.keys import mapbox_access_token
from dateutil.parser import parse
from rest_framework import status
from rest_framework.reverse import reverse
from rest_framework.test import APITestCase, APIClient, force_authenticate
from jose import jws
from moto import mock_iot
from geojson import Feature, FeatureCollection, LineString, Point
import httpretty
import json
import os
import re
import copy
from conf import test_settings
from unittest.mock import patch

from apps.shipments.rpc import Load110RPCClient
from apps.shipments.models import Shipment, Location, LoadShipment, FundingType, Device, TrackingData
from apps.authentication import AuthenticatedUser
from apps.utils import random_id
from tests.utils import replace_variables_in_string, create_form_content

from apps.shipments.views import ShipmentViewSet

boto3.setup_default_session()  # https://github.com/spulec/moto/issues/1926

VAULT_ID = 'b715a8ff-9299-4c87-96de-a4b0a4a54509'
CARRIER_WALLET_ID = '3716ff65-3d03-4b65-9fd5-43d15380cff9'
SHIPPER_WALLET_ID = '48381c16-432b-493f-9f8b-54e88a84ec0a'
STORAGE_CRED_ID = '77b72202-5bcd-49f4-9860-bc4ec4fee07b'
DEVICE_ID = '332dc6c8-b89e-449e-a802-0bfe760f83ff'
OWNER_ID = '332dc6c8-b89e-449e-a802-0bfe760f83ff'
LOCATION_NAME = "Test Location Name"
LOCATION_NAME_2 = "Second Test Location Name"
LOCATION_CITY = 'City'
LOCATION_STATE = 'State'
LOCATION_NUMBER = '555-555-5555'

mapbox_url = re.compile(r'https://api.mapbox.com/geocoding/v5/mapbox.places/[\w$\-@&+%,]+.json')
google_url = f'https://maps.googleapis.com/maps/api/geocode/json'


private_key = b"""-----BEGIN RSA PRIVATE KEY-----
MIICXgIBAAKBgQDtAMh97vXP8KnZUEUrnUT8nz0+8oLrOfBB19+eLIDfNvACNA2D
swOK9gCY+/QcOCR+c5yGTe8lCNwlwW42ingABeM5PigYZ1AfNHVPatcLzO9u3dZG
WMsAB6Un9xmaJfIuKv85jX7Wu9Pkq7EaZbr8pbbMNcYiX1amCrXggZDWOQIDAQAB
AoGBAINMQsZZov5+8mm86YUfDH/zbAe6bEMKhwrDIFRNjVub4N0nnzEN9HGAlZYr
RvJ3O+h9/gH9nPXkcanM/lTi41T27Vn2TZ9Fp71BwOVgnaisjwtY01AIASTl8gWA
rwleIhGY3Kbw6D7V5lqyr8UWsi20SBc9+EILF+ugpUZoXbWtAkEA/GikOeojxPJa
L3MPD+Bc6pz570VpYYtkDUHH9gJgVSb/xohNWoA4zT71rxjD0yjA06mhgxWqg3PP
WAZ9276gkwJBAPBgB2SaibmtP7efiWZfMNUGo2J6t47g7B5wv2C/YmSO2twlaik6
SL2wXVzLnU/Phmjb+bbjYE5hVASlenRSiYMCQGl1dxhTgXpqH9AvbJ2finLj/3E/
ORZuXPFFCLz6pTEuyDM1A8zKQfFPWus7l6YEIvzMpRTV2pZtrrYCkFddwE0CQQCi
IHL8FQuts7/VLwKyjKPYGukaZCDoeqZnha5fJ9bKclwFviqTch9b6dee3irViOhk
U3JjO4tacmUD2UT1rjHXAkEAjpPF0Zdv4Dbf52MfeowoLw/KyreQfRVCIeSG9A4H
3xlhpEJUcgzUV1E2BJRitz2w6ItAFm9Lhx7EPO4ZPHPylQ==
-----END RSA PRIVATE KEY-----"""


class ShipmentAPITests(APITestCase):

    def setUp(self):
        self.client = APIClient()

        self.user_1 = AuthenticatedUser({
            'user_id': '5e8f1d76-162d-4f21-9b71-2ca97306ef7b',
            'username': 'user1@shipchain.io',
            'email': 'user1@shipchain.io',
        })

    def set_user(self, user, token=None):
        self.client.force_authenticate(user=user, token=token)

    def create_shipment(self):
        self.shipments = []
        self.shipments.append(Shipment.objects.create(vault_id=VAULT_ID,
                                                      carrier_wallet_id=CARRIER_WALLET_ID,
                                                      shipper_wallet_id=SHIPPER_WALLET_ID,
                                                      storage_credentials_id=STORAGE_CRED_ID,
                                                      pickup_estimated="2018-11-10T17:57:05.070419Z",
                                                      owner_id=self.user_1.id))
        self.shipments.append(Shipment.objects.create(vault_id=VAULT_ID,
                                                      carrier_wallet_id=CARRIER_WALLET_ID,
                                                      shipper_wallet_id=SHIPPER_WALLET_ID,
                                                      storage_credentials_id=STORAGE_CRED_ID,
                                                      pickup_estimated="2018-11-05T17:57:05.070419Z",
                                                      mode='mode',
                                                      owner_id=self.user_1.id))

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

        response = self.client.get(f'{url}?mode=mode')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        response_data = response.json()
        self.assertEqual(len(response_data['data']), 1)

        setattr(self.shipments[1], 'ship_to_location', Location.objects.create(name="locat"))
        self.shipments[1].save()

        response = self.client.get(f'{url}?ship_to_location__name=locat')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        response_data = response.json()
        self.assertEqual(len(response_data['data']), 1)

        response = self.client.get(f'{url}?has_ship_to_location=true')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        response_data = response.json()
        self.assertEqual(len(response_data['data']), 1)

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

        response = self.client.get(f'{url}?ordering=pickup_estimated')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        response_data = response.json()
        self.assertEqual(response_data['data'][0]['id'], self.shipments[1].id)

        response = self.client.get(f'{url}?ordering=-pickup_estimated')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        response_data = response.json()
        self.assertEqual(response_data['data'][0]['id'], self.shipments[0].id)

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
                    'source': 'gps',
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
            self.assertEqual(data_from_db[0].device_id.id, track_dic['device_id'])
            self.assertTrue(isinstance(data_from_db[0].shipment, Shipment))
            self.assertEqual(data_from_db[0].latitude, track_dic['position']['latitude'])

            # Get tracking data
            response = self.client.get(url)

            # Unauthenticated request should fail
            self.assertEqual(response.status_code, 403)

            # Authenticated request should succeed
            self.set_user(self.user_1)
            response = self.client.get(url)
            self.assertTrue(response.status_code, status.HTTP_200_OK)
            data = response.data
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
            data = response.data
            self.assertEqual(len(data['features']), 3)

            # We expect the second point data to be the first in LineString
            # since it has been  generated first. See timestamp values
            pos = track_dic_2['position']
            self.assertEqual(data['features'][0]['geometry']['coordinates'][0], [pos['longitude'], pos['latitude']])

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
        token = jwt.encode({'email': 'a@domain.com', 'username': 'a@domain.com', 'aud': '11111'},
                           private_key, algorithm='RS256',
                           headers={'kid': '230498151c214b788dd97f22b85410a5', 'aud': '11111'})
        self.set_user(self.user_1, token)

        post_data = replace_variables_in_string(post_data, parameters)

        httpretty.register_uri(httpretty.GET,
                               f"{test_settings.PROFILES_URL}/api/v1/wallet/{parameters['_shipper_wallet_id']}/",
                               body=json.dumps({'good': 'good'}), status=status.HTTP_200_OK)
        httpretty.register_uri(httpretty.GET,
                               f"{test_settings.PROFILES_URL}/api/v1/storage_credentials/{parameters['_storage_credentials_id']}/",

                               body=json.dumps({'good': 'good'}), status=status.HTTP_200_OK)

        response = self.client.post(url, post_data, content_type='application/vnd.api+json')
        force_authenticate(response, user=self.user_1, token=token)

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
    def test_create_with_location(self):
        url = reverse('shipment-list', kwargs={'version': 'v1'})

        # Unauthenticated request should fail with 403
        response = self.client.post(url, '{}', content_type='application/vnd.api+json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

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

        one_location, content_type = create_form_content({'ship_from_location.name': LOCATION_NAME,
                                                          'ship_from_location.city': LOCATION_CITY,
                                                          'ship_from_location.state': LOCATION_STATE,
                                                          'carrier_wallet_id': CARRIER_WALLET_ID,
                                                          'shipper_wallet_id': SHIPPER_WALLET_ID,
                                                          'storage_credentials_id': STORAGE_CRED_ID
                                                          })

        one_location_profiles_disabled, content_type = create_form_content({'ship_from_location.name': LOCATION_NAME,
                                                                            'ship_from_location.city': LOCATION_CITY,
                                                                            'ship_from_location.state': LOCATION_STATE,
                                                                            'ship_from_location.owner_id': OWNER_ID,
                                                                            'carrier_wallet_id': CARRIER_WALLET_ID,
                                                                            'shipper_wallet_id': SHIPPER_WALLET_ID,
                                                                            'storage_credentials_id': STORAGE_CRED_ID,
                                                                            'owner_id': OWNER_ID
                                                                           })

        two_locations, content_type = create_form_content({'ship_from_location.name': LOCATION_NAME,
                                                           'ship_from_location.city': LOCATION_CITY,
                                                           'ship_from_location.state': LOCATION_STATE,
                                                           'ship_to_location.name': LOCATION_NAME_2,
                                                           'ship_to_location.city': LOCATION_CITY,
                                                           'ship_to_location.state': LOCATION_STATE,
                                                           'carrier_wallet_id': CARRIER_WALLET_ID,
                                                           'shipper_wallet_id': SHIPPER_WALLET_ID,
                                                           'storage_credentials_id': STORAGE_CRED_ID
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

        google_obj = {'results': [{'address_components': [{'types': []}], 'geometry': {'location': {'lat': 12, 'lng': 23}}}]}
        mapbox_obj = {'features': [{'place_type': [{'types': []}], 'geometry': {'coordinates': [23, 12]}}]}

        httpretty.register_uri(httpretty.GET, google_url, body=json.dumps(google_obj))
        httpretty.register_uri(httpretty.GET, mapbox_url, body=json.dumps(mapbox_obj))
        httpretty.register_uri(httpretty.GET,
                               f"{test_settings.PROFILES_URL}/api/v1/wallet/{parameters['_shipper_wallet_id']}/",
                               body=json.dumps({'good': 'good'}), status=status.HTTP_200_OK)
        httpretty.register_uri(httpretty.GET,
                               f"{test_settings.PROFILES_URL}/api/v1/storage_credentials/{parameters['_storage_credentials_id']}/",
                               body=json.dumps({'good': 'good'}), status=status.HTTP_200_OK)

        # Authenticated request should succeed using mapbox (if exists)
        token = jwt.encode({'email': 'a@domain.com', 'username': 'a@domain.com', 'aud': '11111'},
                           private_key, algorithm='RS256',
                           headers={'kid': '230498151c214b788dd97f22b85410a5', 'aud': '11111'})
        self.set_user(self.user_1, token)

        response = self.client.post(url, one_location, content_type=content_type)

        force_authenticate(response, user=self.user_1, token=token)
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
        self.assertEqual(ship_from_location.geometry.coords, (12.0, 23.0))

        # Authenticated request should succeed using mapbox in creating two locations (if exists)
        response = self.client.post(url, two_locations, content_type=content_type)
        force_authenticate(response, token=token)
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
        self.assertEqual(ship_from_location.geometry.coords, (12.0, 23.0))

        self.assertIsNotNone(response_data['relationships']['ship_to_location']['data'])
        self.assertEqual(len(response_included), 3)
        ship_to_location = Location.objects.get(id=response_data['relationships']['ship_to_location']['data']['id'])
        self.assertEqual(ship_to_location.city, parameters['_ship_to_location_city'])
        self.assertEqual(ship_to_location.state, parameters['_ship_to_location_state'])
        self.assertEqual(ship_to_location.name, parameters['_ship_to_location_name'])
        self.assertEqual(ship_to_location.geometry.coords, (12.0, 23.0))

        # Authenticated request should succeed using google
        mapbox_access_token = None

        response = self.client.post(url, one_location, content_type=content_type)
        force_authenticate(response, user=self.user_1, token=token)
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
        self.assertEqual(ship_from_location.geometry.coords, (12.0, 23.0))

        # Authenticated request should succeed using google in creating two locations
        response = self.client.post(url, two_locations, content_type=content_type)
        force_authenticate(response, user=self.user_1, token=token)
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
        self.assertEqual(ship_from_location.geometry.coords, (12.0, 23.0))

        self.assertIsNotNone(response_data['relationships']['ship_to_location']['data'])
        self.assertEqual(len(response_included), 3)
        ship_to_location = Location.objects.get(id=response_data['relationships']['ship_to_location']['data']['id'])
        self.assertEqual(ship_to_location.city, parameters['_ship_to_location_city'])
        self.assertEqual(ship_to_location.state, parameters['_ship_to_location_state'])
        self.assertEqual(ship_to_location.name, parameters['_ship_to_location_name'])
        self.assertEqual(ship_to_location.geometry.coords, (12.0, 23.0))

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

    def test_get_device_request_url(self):

        _shipment_id = 'b715a8ff-9299-4c87-96de-a4b0a4a54509'
        _vault_id = '01fc36c4-63e5-4c02-943a-b52cd25b235b'
        shipment = Shipment.objects.create(id=_shipment_id, vault_id=_vault_id)

        profiles_url = shipment.get_device_request_url()

        # http://INTENTIONALLY_DISCONNECTED:9999/api/v1/device/?on_shipment=b715a8ff-9299-4c87-96de-a4b0a4a54509
        self.assertIn(test_settings.PROFILES_URL, profiles_url)
        self.assertIn(f"?on_shipment={_shipment_id}", profiles_url)

    # def test_get_tracking(self):
    #     from datetime import datetime
    #
    #     print('Datetime: ', datetime.now())
    #
    #     self.create_shipment()
    #
    #     url = reverse('shipment-tracking', kwargs={'version': 'v1', 'pk': self.shipments[0].id})
    #
    #     class DeviceForShipmentResponse(object):
    #         status_code = status.HTTP_200_OK
    #
    #         @staticmethod
    #         def json():
    #             return {
    #                 'data': [
    #                     {
    #                         'type': 'Device'
    #                     }
    #                 ]
    #             }
    #
    #     tracking_data = [
    #                 {
    #                     "position":
    #                         {
    #                             "latitude": -80.123635,
    #                             "longitude": 33.018413333333335,
    #                             "altitude": 924,
    #                             "source": "gps",
    #                             "certainty": 95,
    #                             "speed": 34
    #
    #                         },
    #                     "version": "1.0.0",
    #                     "device_id": DEVICE_ID
    #                 },
    #                 {
    #                     "position":
    #                         {
    #                             "latitude": -81.123635,
    #                             "longitude": 33.018413333333335,
    #                             "altitude": 924,
    #                             "source": "gps",
    #                             "certainty": 95,
    #                             "speed": 34
    #
    #                         },
    #                     "version": "1.0.0",
    #                     "device_id": DEVICE_ID
    #                 }
    #             ]
    #
    #     geo_json = {
    #         'type': 'FeatureCollection',
    #         'features': [
    #             {
    #                 'type': 'Feature',
    #                 'geometry': {
    #                     'type': 'LineString',
    #                     'coordinates': [
    #                         [
    #                             -80.123635,
    #                             33.018413333333335
    #                         ],
    #                         [
    #                             -81.123635,
    #                             34.018413333333335
    #                         ]
    #                     ]
    #                 },
    #                 'properties': {
    #                     'linestringTimestamps': [
    #                         '2018-07-27T21:07:14',
    #                         '2018-07-28T21:07:14'
    #                     ]
    #                 }
    #             },
    #             {
    #                 'type': 'Feature',
    #                 'geometry': {
    #                     'type': 'Point',
    #                     'coordinates': [
    #                         -80.123635,
    #                         33.018413333333335
    #                     ]
    #                 },
    #                 'properties': {
    #                     'time': '2018-07-27T21:07:14',
    #                     'uncertainty': 0,
    #                     'has_gps': 'A',
    #                     'source': 'gps'
    #                 }
    #             },
    #             {
    #                 'type': 'Feature',
    #                 'geometry': {
    #                     'type': 'Point',
    #                     'coordinates': [
    #                         -81.123635,
    #                         34.018413333333335
    #                     ]
    #                 },
    #                 'properties': {
    #                     'time': '2018-07-28T21:07:14',
    #                     'uncertainty': 0,
    #                     'has_gps': None,
    #                     'source': 'gps'
    #                 }
    #             }
    #         ]
    #     }
    #
    #     # Unauthenticated request should fail with 403
    #     response = self.client.get(url)
    #     self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
    #
    #     # Mock Requests calls
    #     mock_requests = requests
    #     mock_requests.get = mock.Mock(return_value=DeviceForShipmentResponse)
    #
    #     # Mock RPC calls
    #     mock_rpc_client = ShipmentRPCClient
    #     mock_rpc_client.get_tracking_data = mock.Mock(return_value=tracking_data)
    #
    #     # Authenticated request should succeed, pass in token so we can pull it from request.auth
    #     self.set_user(self.user_1, b'a1234567890b1234567890')
    #
    #     response = self.client.get(url)
    #     print(response.content)
    #     response_data = response.json()['data']
    #
    #     self.assertEqual(response_data, geo_json)
    #
    #     # Test ?as_point
    #     response = self.client.get(f'{url}?as_point')
    #     response_json = response.json()
    #
    #     geo_json_point = copy.deepcopy(geo_json)
    #     del geo_json_point['features'][0]
    #
    #     self.assertEqual(response_json['data'], geo_json_point)
    #
    #     # Test ?as_line
    #     response = self.client.get(f'{url}?as_line')
    #     response_data = response.json()['data']
    #
    #     geo_json_line = copy.deepcopy(geo_json)
    #     del geo_json_line['features'][2]
    #     del geo_json_line['features'][1]
    #
    #     self.assertEqual(response_data, geo_json_line)

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
            '_carrier_scac': 'test_scac'
        }

        post_data = '''
                    {
                      "data": {
                        "type": "Shipment",
                        "id": "<<_shipment_id>>",
                        "attributes": {
                          "carrier_scac": "test_scac"
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
        self.assertEqual(response_data['attributes']['carrier_scac'], parameters['_carrier_scac'])
        self.assertEqual(response_data['attributes']['vault_id'], parameters['_vault_id'])
        self.assertIsNotNone(response_data['meta']['async_job_id'])

    @httpretty.activate
    def test_update_with_location(self):
        self.create_shipment()
        url = reverse('shipment-detail', kwargs={'version': 'v1', 'pk': self.shipments[0].id})

        # Unauthenticated request should fail with 403
        response = self.client.patch(url, '{}', content_type='application/vnd.api+json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

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

        google_obj = {'results': [{'address_components': [{'types': []}], 'geometry': {'location': {'lat': 12, 'lng': 23}}}]}
        mapbox_obj = {'features': [{'place_type': [{'types': []}], 'geometry': {'coordinates': [23, 12]}}]}

        httpretty.register_uri(httpretty.GET, google_url, body=json.dumps(google_obj))
        httpretty.register_uri(httpretty.GET, mapbox_url, body=json.dumps(mapbox_obj))

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
        self.assertEqual(ship_from_location.geometry.coords, (12.0, 23.0))

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
        self.assertEqual(ship_from_location.geometry.coords, (12.0, 23.0))

        self.assertIsNotNone(response_data['relationships']['ship_to_location']['data'])
        self.assertEqual(len(response_included), 3)
        ship_to_location = Location.objects.get(id=response_data['relationships']['ship_to_location']['data']['id'])
        self.assertEqual(ship_to_location.city, parameters['_ship_to_location_city'])
        self.assertEqual(ship_to_location.state, parameters['_ship_to_location_state'])
        self.assertEqual(ship_to_location.name, parameters['_ship_to_location_name'])
        self.assertEqual(ship_to_location.geometry.coords, (12.0, 23.0))

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
        self.assertEqual(ship_from_location.geometry.coords, (12.0, 23.0))

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
        self.assertEqual(ship_from_location.geometry.coords, (12.0, 23.0))

        self.assertIsNotNone(response_data['relationships']['ship_to_location']['data'])
        self.assertEqual(len(response_included), 3)
        ship_to_location = Location.objects.get(id=response_data['relationships']['ship_to_location']['data']['id'])
        self.assertEqual(ship_to_location.city, parameters['_ship_to_location_city'])
        self.assertEqual(ship_to_location.state, parameters['_ship_to_location_state'])
        self.assertEqual(ship_to_location.name, parameters['_ship_to_location_name'])
        self.assertEqual(ship_to_location.geometry.coords, (12.0, 23.0))


class LocationAPITests(APITestCase):

    def setUp(self):
        self.client = APIClient()

        os.environ['MAPBOX_ACCESS_TOKEN'] = 'pk.test'

        self.user_1 = AuthenticatedUser({
            'user_id': '5e8f1d76-162d-4f21-9b71-2ca97306ef7b',
            'username': 'user1@shipchain.io',
            'email': 'user1@shipchain.io',
        })

    def set_user(self, user, token=None):
        self.client.force_authenticate(user=user, token=token)

    def create_location(self):
        self.locations = []
        self.locations.append(Location.objects.create(name=LOCATION_NAME,
                                                      owner_id='5e8f1d76-162d-4f21-9b71-2ca97306ef7b'))

    def test_list_empty(self):
        """
        Test listing requires authentication
        """

        # Unauthenticated request should fail with 403
        url = reverse('location-list', kwargs={'version': 'v1'})

        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        # Authenticated request should succeed
        self.set_user(self.user_1)

        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        response_data = response.json()

        # No Locations
        #  created should return empty array
        self.assertEqual(len(response_data['data']), 0)

    @httpretty.activate
    def test_create_location(self):
        url = reverse('location-list', kwargs={'version': 'v1'})
        valid_data, content_type = create_form_content({'name': LOCATION_NAME, 'city': LOCATION_CITY,
                                                        'state': LOCATION_STATE})

        valid_data_profiles_disabled, content_type = create_form_content({'name': LOCATION_NAME, 'city': LOCATION_CITY,
                                                                          'state': LOCATION_STATE,
                                                                          'owner_id': OWNER_ID})

        google_obj = {'results': [{'address_components': [{'types': []}], 'geometry': {'location': {'lat': 12, 'lng': 23}}}]}
        mapbox_obj = {'features': [{'place_type': [{'types': []}], 'geometry': {'coordinates': [23, 12]}}]}

        httpretty.register_uri(httpretty.GET, google_url, body=json.dumps(google_obj))
        httpretty.register_uri(httpretty.GET, mapbox_url, body=json.dumps(mapbox_obj))

        # Unauthenticated request should fail with 403
        response = self.client.post(url, valid_data, content_type=content_type)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        self.set_user(self.user_1)

        # Authenticated request without name parameter should fail
        response = self.client.post(url, '{}', content_type=content_type)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        # Authenticated request with name parameter using mapbox should succeed
        response = self.client.post(url, valid_data, content_type=content_type)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        response_data = response.json()
        self.assertEqual(response_data['data']['attributes']['name'], LOCATION_NAME)
        self.assertEqual(response_data['data']['attributes']['geometry']['coordinates'], [12.0, 23.0])

        mapbox_access_token = None

        # Authenticated request with name parameter using google should succeed
        response = self.client.post(url, valid_data, content_type=content_type)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        response_data = response.json()
        self.assertEqual(response_data['data']['attributes']['name'], LOCATION_NAME)
        self.assertEqual(response_data['data']['attributes']['geometry']['coordinates'], [12.0, 23.0])

        with self.settings(PROFILES_ENABLED=False, PROFILES_URL='DISABLED'):
            response = self.client.post(url, valid_data_profiles_disabled, content_type=content_type)
            print(response.content)
            self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    @httpretty.activate
    def test_update_existing_location(self):
        self.create_location()
        url = reverse('location-detail', kwargs={'version': 'v1', 'pk': self.locations[0].id})
        valid_data, content_type = create_form_content({'phone_number': LOCATION_NUMBER, 'city': LOCATION_CITY,
                                                        'state': LOCATION_STATE})
        google_obj = {
            'results': [{'address_components': [{'types': []}], 'geometry': {'location': {'lat': 12, 'lng': 23}}}]}
        mapbox_obj = {
            'features': [{'place_type': [{'types': []}], 'geometry': {'coordinates': [23, 12]}}]}

        httpretty.register_uri(httpretty.GET, google_url, body=json.dumps(google_obj))
        httpretty.register_uri(httpretty.GET, mapbox_url, body=json.dumps(mapbox_obj))

        # Unauthenticated request should fail with 403
        response = self.client.patch(url, valid_data, content_type=content_type)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        self.set_user(self.user_1)

        # Authenticated request with name parameter using mapbox should succeed
        response = self.client.patch(url, valid_data, content_type=content_type)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        response_data = response.json()
        self.assertEqual(response_data['data']['attributes']['phone_number'], LOCATION_NUMBER)
        self.assertEqual(response_data['data']['attributes']['geometry']['coordinates'], [12.0, 23.0])

        mapbox_access_token = None

        # Authenticated request with name parameter using google should succeed
        response = self.client.patch(url, valid_data, content_type=content_type)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        response_data = response.json()
        self.assertEqual(response_data['data']['attributes']['phone_number'], LOCATION_NUMBER)
        self.assertEqual(response_data['data']['attributes']['geometry']['coordinates'], [12.0, 23.0])

    def test_update_nonexistent_location(self):
        self.create_location()
        url = reverse('location-detail', kwargs={'version': 'v1', 'pk': random_id()})
        valid_data, content_type = create_form_content({'phone_number': LOCATION_NUMBER})

        # Unauthenticated request should fail with 403
        response = self.client.patch(url, valid_data, content_type=content_type)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        self.set_user(self.user_1)

        # Authenticated request should fail
        response = self.client.patch(url, valid_data, content_type=content_type)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_delete_existing_location(self):
        self.create_location()
        url = reverse('location-detail', kwargs={'version': 'v1', 'pk': self.locations[0].id})

        # Unauthenticated request should fail with 403
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        self.set_user(self.user_1)

        # Authenticated request should succeed
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

        # Ensure location does not exist
        self.assertEqual(Location.objects.count(), 0)

    def test_delete_nonexistent_location(self):
        self.create_location()
        url = reverse('location-detail', kwargs={'version': 'v1', 'pk': random_id()})

        # Unauthenticated request should fail with 403
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        self.set_user(self.user_1)

        # Authenticated request should fail
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class TrackingDataAPITests(APITestCase):

    def setUp(self):
        self.client = APIClient()

        self.user_1 = AuthenticatedUser({
            'user_id': '5e8f1d76-162d-4f21-9b71-2ca97306ef7b',
            'username': 'user1@shipchain.io',
            'email': 'user1@shipchain.io',
        })

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
                                                              device_id=Device.objects.create(certificate_id='My-Custom-Device'),
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
