"""Synthetic Google payloads: never contains user records or live API data."""
def place(identifier='fixture-chiyoda', name='セブン-イレブン 千代田店', address='東京都千代田区二番町8-8', coordinates=(139.737, 35.685)):
    value = {'id': identifier, 'displayName': {'text': name, 'languageCode': 'ja'},
             'formattedAddress': address, 'types': ['convenience_store', 'establishment'],
             'addressComponents': [], 'googleMapsUri': 'https://maps.google.com/?cid=fixture', 'attributions': []}
    if coordinates is not None:
        value['location'] = {'longitude': coordinates[0], 'latitude': coordinates[1]}
    return value
