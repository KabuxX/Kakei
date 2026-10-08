"""Transaction references retain user identity but never provider content."""
import json
from services.receipt_location_contracts import METHODS, normalize_location_input
from services.validation import ValidationError

def read_merchant_place(connection, transaction_id) -> dict | None:
    row = connection.execute('SELECT provider,place_id,method,input_json,confirmed_at FROM transaction_merchant_places WHERE transaction_id=?', (transaction_id,)).fetchone()
    if row is None:
        return None
    return dict(provider=row[0], placeId=row[1], method=row[2], input=json.loads(row[3]), confirmedAt=row[4])

def write_merchant_place(connection, transaction_id, binding: dict) -> None:
    if binding.get('provider') != 'google' or not isinstance(binding.get('placeId'), str) or not binding['placeId'].strip() or binding.get('method') not in METHODS:
        raise ValidationError('merchantPlace', '地点参照を確認してください。')
    connection.execute('''INSERT INTO transaction_merchant_places VALUES (?,?,?,?,?,?)
        ON CONFLICT(transaction_id) DO UPDATE SET provider=excluded.provider,place_id=excluded.place_id,
        method=excluded.method,input_json=excluded.input_json,confirmed_at=excluded.confirmed_at''',
        (transaction_id, 'google', binding['placeId'], binding['method'], json.dumps(normalize_location_input(binding['input']), ensure_ascii=False), binding['confirmedAt']))

def clear_merchant_place(connection, transaction_id) -> None:
    connection.execute('DELETE FROM transaction_merchant_places WHERE transaction_id=?', (transaction_id,))

def merchant_place_projection(binding: dict) -> dict:
    return {key: binding[key] for key in ('provider', 'placeId', 'method')}


def read_merchant_places(connection) -> dict:
    return {row['transaction_id']: dict(provider=row['provider'], placeId=row['place_id'],
        method=row['method'], input=json.loads(row['input_json']), confirmedAt=row['confirmed_at'])
        for row in connection.execute('SELECT * FROM transaction_merchant_places')}


def should_clear_merchant_place(old: dict, draft: dict, *, address_only=False) -> bool:
    from services.merchant_address import normalize_merchant_address
    if address_only:
        return True
    merchant = lambda value: value.strip() if isinstance(value, str) else value
    return (draft.get('type', old.get('type')) == 'income'
        or merchant(draft.get('merchant', old.get('merchant'))) != merchant(old.get('merchant'))
        or ('merchantAddress' in draft and normalize_merchant_address(draft['merchantAddress'])
            != normalize_merchant_address(old.get('merchantAddress'))))
