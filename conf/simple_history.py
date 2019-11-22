

SIMPLE_HISTORY_HISTORY_ID_USE_UUID = True

SIMPLE_HISTORY_EDIT = False

# Related objects time query window in milliseconds
SIMPLE_HISTORY_RELATED_WINDOW_MS = 1000

RELATED_FIELDS_WITH_HISTORY_MAP = {
    'ship_from_location': 'Location',
    'ship_to_location': 'Location',
    'final_destination_location': 'Location',
    'bill_to_location': 'Location',
    'shipment': 'Shipment'
}
