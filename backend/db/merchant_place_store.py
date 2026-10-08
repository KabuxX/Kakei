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
