import pytest


@pytest.mark.django_db
def test_shadow_geofence_updates(mocked_iot_api, shipment_with_device):
    call_count = mocked_iot_api.call_count
    shipment_with_device.geofences = ['testing123', 'testing124']
    shipment_with_device.save()
    call_count += 1  # Geofence should have been updated in the shadow
    assert mocked_iot_api.call_count == call_count
    mocked_iot_api.assert_called_with(shipment_with_device.device_id, {'geofences': shipment_with_device.geofences})

    shipment_with_device.geofences = None
    shipment_with_device.save()
    call_count += 1  # Geofence should have been updated in the shadow
    assert mocked_iot_api.call_count == call_count
    mocked_iot_api.assert_called_with(shipment_with_device.device_id, {'geofences': None})

    shipment_with_device.geofences = []
    shipment_with_device.save()
    call_count += 1  # Geofence should have been updated in the shadow
    assert mocked_iot_api.call_count == call_count
    mocked_iot_api.assert_called_with(shipment_with_device.device_id, {'geofences': []})


# TODO: check geofence CRUD, serialization
# TODO: check geofence_id uniqueness
