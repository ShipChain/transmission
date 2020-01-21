"""
Copyright 2020 ShipChain, Inc.

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

import argparse
import logging
import random
import time

import django
import requests

from .auth import GetSessionJwt

django.setup()

LOG = logging.getLogger('transmission')

parser = argparse.ArgumentParser()

parser.add_argument('-s', action='store',
                    dest='shipment_id',
                    required=True,
                    help='UUID of the shipment to update')

parser.add_argument('-c', action='store',
                    dest='client_id',
                    required=True,
                    help='Profiles client ID')

parser.add_argument('-u', action='store',
                    dest='username',
                    required=True,
                    help='Profiles username')

parser.add_argument('-p', action='store',
                    dest='password',
                    required=True,
                    help='Profiles password')

parser.add_argument('-n', action='store',
                    dest='changes_number',
                    required=True,
                    type=int,
                    help='Number of changes to perform')

parser.add_argument('-p-host', action='store',
                    dest='profiles_host',
                    default='profiles-runserver:8000',
                    help='Profiles host name, required for environment different than local')

parser.add_argument('-env', action='store',
                    dest='env',
                    default='LOCAL',
                    help='Deployment environment')

parser.add_argument('-t-host', action='store',
                    dest='transmission_host',
                    default='transmission-runserver:8000',
                    help='Transmission host name, required for environment different than local')

LOCATION_ATTRIBUTES = ('ship_from_location', 'ship_to_location', 'final_destination_location', 'bill_to_location', )

LOCATION_CANDIDATES = (
    {
        'name': 'Greenville',
        'state': 'South Carolina',
        'country': 'US',
        'postal_code': '29601',
    },
    {
        'name': 'L.A',
        'state': 'California',
        'country': 'US',
        'postal_code': '90001',
    },
    {
        'name': 'Montreal',
        'state': 'Quebec',
        'country': 'CA',
        'postal_code': 'H1A 0A1',
    },
    {
        'name': 'Dallas',
        'state': 'Texas',
        'country': 'US',
        'postal_code': '75001',
    },
    {
        'name': 'Miami',
        'state': 'Florida',
        'country': 'US',
        'postal_code': '33101',
    },
)


def get_random_number(begin, end):
    random.seed()
    return random.randint(begin, end)


def get_random_document_data():
    from apps.documents.models import DocumentType, FileType
    candidates = [
        {
           'name': 'Test BOL ' + str(get_random_number(1, 999)),
           'file_type': FileType.PDF.name,
           'document_type': DocumentType.BOL.name,
        },
        {
           'name': 'Shipment Image png ' + str(get_random_number(1, 999)),
           'file_type': FileType.PNG.name,
           'document_type': DocumentType.IMAGE.name,
        },
        {
           'name': 'Shipment Image jpeg ' + str(get_random_number(1, 999)),
           'file_type': FileType.JPEG.name,
           'document_type': DocumentType.IMAGE.name,
        },
    ]

    return candidates[get_random_number(0, len(candidates) - 1)]


def get_shipment_fields():
    fields = {}
    candidates = [
        {
            'package_qty': get_random_number(1, 1234),
        },
        {
            'vessel_name': f'Vessel Number: {get_random_number(1, 1234)}',
        },
        {
            'voyage_number': f'Voyager Number: {get_random_number(1, 1234)}',
        },
        {
            'weight_chargeable': f'{get_random_number(1, 999)}.{get_random_number(1, 99)}',
        },
        {
            'volume': f'{get_random_number(1, 999)}.{get_random_number(1, 99)}',
        },
    ]

    number_of_field = get_random_number(0, len(candidates))

    for numb in range(0, number_of_field):
        fields.update(candidates[get_random_number(0, number_of_field - 1)])

    return fields


def get_object_id(object_dict):
    try:
        return object_dict['id']
    except KeyError:
        return object_dict['data']['id']


def get_locations():
    locations = {}
    num_locations = get_random_number(0, len(LOCATION_ATTRIBUTES) - 1)

    for num in range(0, num_locations):
        location_attr_name = LOCATION_ATTRIBUTES[get_random_number(0, len(LOCATION_ATTRIBUTES) - 1)]
        location_candidate = LOCATION_CANDIDATES[get_random_number(0, len(LOCATION_ATTRIBUTES) - 1)]
        location = {f'{location_attr_name}.{attr}': value for attr, value in location_candidate.items()}
        locations = {**locations, **location}

    return locations


def create_shipment_documents(document_url, doc_number, jwt):
    created_documents = []
    for num_doc in range(0, doc_number):
        response = requests.post(document_url, data=get_random_document_data(),
                                 headers={'Authorization': f'JWT {jwt}'}).json()

        LOG.debug(f'Created document: {[get_object_id(response)]}')
        created_documents.append(response)

    return created_documents


def mark_documents_upload_status_complete(base_document_url, documents_list,  jwt):
    from apps.documents.models import UploadStatus

    complete_documents = []
    for document in documents_list:
        response = requests.patch(f'{base_document_url}/{get_object_id(document)}/',
                                  data={'upload_status': UploadStatus.COMPLETE.name},
                                  headers={'Authorization': f'JWT {jwt}'}
                                  ).json()

        LOG.debug(f'Document: {[get_object_id(response)]}, marked as [COMPLETE]')
        complete_documents.append(response)

    return complete_documents


def random_update_document_description(base_document_url, documents_list,  jwt):
    description = f'Random Document Description: {get_random_number(1, 9999)}'
    for document in documents_list:
        response = requests.patch(f'{base_document_url}/{get_object_id(document)}/',
                                  data={'description': description},
                                  headers={'Authorization': 'JWT {}'.format(jwt)}
                                  ).json()

        LOG.debug(f'Updated document: {[get_object_id(response)]}, with description: [{description}]')


def update_shipment(shipment_url, shipment_fields, locations, jwt):
    shipment_data = {**shipment_fields, **locations}
    requests.patch(shipment_url, data=shipment_data, headers={'Authorization': f'JWT {jwt}'})
    LOG.debug(f'Shipment updated with: {shipment_data}')


if __name__ == '__main__':
    random.seed()
    arguments = parser.parse_args()

    schema = 'http' if arguments.env.lower() == 'local' else 'https'

    document_create_url = f'{schema}://{arguments.transmission_host}/api/v1/shipments/{arguments.shipment_id}/documents'

    shipment_update_url = f'{schema}://{arguments.transmission_host}/api/v1/shipments/{arguments.shipment_id}/'

    jwt_session = GetSessionJwt(username=arguments.username, password=arguments.password,
                                client_id=arguments.client_id, environment=arguments.env,
                                profiles_host=arguments.profiles_host, schema=schema)

    for num_change in range(0, arguments.changes_number):
        documents = create_shipment_documents(
            document_create_url,
            get_random_number(0, 3),
            jwt_session()
        )

        # Sleep for 3s
        time.sleep(2)

        marked_documents = mark_documents_upload_status_complete(document_create_url, documents, jwt_session())

        # Sleep for 3s
        time.sleep(2)

        random_update_document_description(document_create_url, marked_documents, jwt_session())

        # Sleep for 3s
        time.sleep(2)

        update_shipment(
            shipment_update_url,
            get_shipment_fields(),
            get_locations(),
            jwt_session()
        )
