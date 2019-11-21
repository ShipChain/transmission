import pytest
import json

from rest_framework import status
from rest_framework.reverse import reverse

from shipchain_common.utils import random_id
from shipchain_common.test_utils import create_form_content

GEOFENCE_1 = random_id()
GEOFENCE_2 = random_id()
GEOFENCE_3 = random_id()


@pytest.mark.django_db
def test_shadow_geofence_updates(mocked_iot_api, shipment_with_device):
    call_count = mocked_iot_api.call_count
    shipment_with_device.geofences = [GEOFENCE_1, GEOFENCE_2]
    shipment_with_device.save()
    call_count += 1  # Geofence should have been updated in the shadow
    assert mocked_iot_api.call_count == call_count
    mocked_iot_api.assert_called_with(shipment_with_device.device_id, {'geofences': shipment_with_device.geofences})

    shipment_with_device.geofences = None
    shipment_with_device.save()
    call_count += 1  # Geofence should have been updated in the shadow
    assert mocked_iot_api.call_count == call_count
    mocked_iot_api.assert_called_with(shipment_with_device.device_id, {'geofences': ''})

    shipment_with_device.geofences = []
    shipment_with_device.save()
    call_count += 1  # Geofence should have been updated in the shadow (don't send empty arrays to IoT)
    assert mocked_iot_api.call_count == call_count
    mocked_iot_api.assert_called_with(shipment_with_device.device_id, {'geofences': ''})


@pytest.mark.django_db
def test_geofence_updates(api_client, mocked_iot_api, shipment_with_device):
    url = reverse('shipment-detail', kwargs={'version': 'v1', 'pk': shipment_with_device.id})
    shipment_update_request = {
        'geofences': [GEOFENCE_1]
    }
    response = api_client.patch(url, data=shipment_update_request, format='json')
    assert response.status_code == status.HTTP_202_ACCEPTED
    updated_parameters = response.json()['data']['attributes']
    assert updated_parameters['geofences'] == [GEOFENCE_1]

    url = reverse('shipment-detail', kwargs={'version': 'v1', 'pk': shipment_with_device.id})
    shipment_update_request_formdata, content_type = create_form_content({
        "geofences": json.dumps([GEOFENCE_2]),
    })

    response = api_client.patch(url, data=shipment_update_request_formdata, content_type=content_type)
    assert response.status_code == status.HTTP_202_ACCEPTED
    updated_parameters = response.json()['data']['attributes']
    assert updated_parameters['geofences'] == [GEOFENCE_2]


@pytest.mark.django_db
def test_geofence_creates(api_client, mocked_iot_api, mocked_profiles, mocked_engine_rpc):
    url = reverse('shipment-list', kwargs={'version': 'v1'})
    shipment_create_request = {
        "geofences": [GEOFENCE_3],
        **mocked_profiles
    }
    response = api_client.post(url, data=shipment_create_request, format='json')
    assert response.status_code == status.HTTP_202_ACCEPTED
    updated_parameters = response.json()['data']['attributes']
    assert updated_parameters['geofences'] == [GEOFENCE_3]

# TODO: check geofence_id uniqueness
