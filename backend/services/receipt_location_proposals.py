"""Bind server-owned receipt confirmations and apply references atomically."""
from db.receipt_location_store import ReceiptLocationStore, _resolution
from db.merchant_place_store import write_merchant_place, clear_merchant_place, read_merchant_place
from db.store import TrajectoryConflict
from services.receipt_location_contracts import normalize_location_input, location_fingerprint
from services.validation import ValidationError

GOOGLE_METHODS = frozenset(("google_unique","google_selected","existing_google"))

def receipt_location_address(binding):
    return None if binding["method"] in GOOGLE_METHODS else binding["input"]["merchantAddress"]


def bind_receipt_location(connection, thread_id, receipt_id, target, draft, location: dict, *, now) -> dict:
    if not isinstance(location, dict) or not isinstance(draft, dict):
        raise ValidationError('location', '店舗・住所を確認してから変更案を作成してください。')
    row = ReceiptLocationStore._row(connection, thread_id, receipt_id, now)
    if not row or row['id'] != location.get('resolutionId') or type(location.get('revision')) is not int or row['revision'] != location['revision']:
        raise TrajectoryConflict('店舗確認が更新されています。最新の確認を使用してください。')
    resolution = _resolution(row)
    if resolution['status'] != 'resolved' or resolution['expiresAt'] <= now:
        raise ValidationError('location', '店舗・住所の確認が必要です。')
    value = normalize_location_input(location.get('input'))
    if location_fingerprint(value) != resolution['inputFingerprint']:
        raise ValidationError('location', '店舗入力が変わりました。再確認してください。')
    binding = {key: resolution[key] for key in ('input','inputFingerprint','method','selectedPlaceId','confirmedAt','expiresAt','sourceTransactionId')}
    binding.update(resolutionId=resolution['id'], revision=resolution['revision'], target=target)
    if normalize_location_input({'merchant':draft.get('merchant'),'merchantAddress':draft.get('merchantAddress')}) != normalize_location_input({'merchant':value['merchant'],'merchantAddress':value['merchantAddress']}):
        raise ValidationError('location','店舗・住所が変わりました。再確認してください。')
    command = {'kind':'transaction.create' if target == 'new' else 'transaction.update', 'identity':{} if target == 'new' else {'id':target}, 'data':{**draft,'merchantAddress':receipt_location_address(binding),'receiptIds':[receipt_id]}}
    validate_receipt_location({'receiptLocation':binding,'receiptId':receipt_id}, command, now=now)
    source = binding['sourceTransactionId']
    if source:
        record = connection.execute('SELECT merchant,merchant_address FROM transactions WHERE id=?',(source,)).fetchone()
        from services.google_place_resolution import normalize_name
        if not record or normalize_name(record['merchant'] or '') != normalize_name(value['merchant']):
            raise TrajectoryConflict('保存先の店舗が変わりました。再確認してください。')
        if binding['method'] == 'existing_address' and record['merchant_address'] != value['merchantAddress']:
            raise TrajectoryConflict('保存先の住所が変わりました。再確認してください。')
        place = read_merchant_place(connection,source)
        if binding['method'] == 'existing_google' and (not place or place['placeId'] != binding['selectedPlaceId']):
            raise TrajectoryConflict('保存先の地点参照が変わりました。再確認してください。')
    return binding


def validate_receipt_location(metadata: dict, command: dict, *, now) -> None:
    if 'receiptLocation' not in metadata:
        return  # Only already-issued legacy proposals lack this metadata.
    binding = metadata['receiptLocation']
    required = {'input','inputFingerprint','method','selectedPlaceId','expiresAt','sourceTransactionId','target'}
    if not isinstance(binding,dict) or not required <= binding.keys():
        raise ValidationError('location','店舗確認を再確認してください。')
    target = 'new' if command['kind'] == 'transaction.create' else command['identity'].get('id')
    if binding['expiresAt'] <= now:
        raise ValidationError('location', '店舗確認の期限が切れています。再確認してください。')
    if binding['target'] != target or (binding['sourceTransactionId'] is not None and binding['sourceTransactionId'] != target):
        raise ValidationError('target', '保存先が変わりました。店舗を再確認してください。')
    data = command['data']; value = normalize_location_input(binding['input'])
    address = receipt_location_address(binding)
    if data.get('type') != 'expense' or normalize_location_input({'merchant':data.get('merchant'),'merchantAddress':data.get('merchantAddress')}) != normalize_location_input({'merchant':value['merchant'],'merchantAddress':address}):
        raise ValidationError('location', '店舗・住所が変わりました。レシート確認で再確認してください。')
    for key in ('branch','locality'):
        if key in data and normalize_location_input({**value,key:data[key]}) != value:
            raise ValidationError('location', '店舗入力が変わりました。再確認してください。')
    if location_fingerprint(value) != binding['inputFingerprint']:
        raise ValidationError('location', '店舗入力を再確認してください。')
    if binding['method'] in GOOGLE_METHODS:
        if not binding['selectedPlaceId'] or 'merchantAddress' not in data or data['merchantAddress'] is not None:
            raise ValidationError('location', '地点参照を再確認してください。')
    elif binding['method'] not in ('receipt_address','user_address','existing_address') or not value['merchantAddress']:
        raise ValidationError('location', '店舗住所を再確認してください。')
    if metadata.get('receiptId') and command['data'].get('receiptIds') != [metadata['receiptId']]:
        raise ValidationError('receiptId', 'レシートの指定が変わっています。')


def apply_receipt_location(connection, transaction_id, binding: dict) -> None:
    if binding['method'] in GOOGLE_METHODS:
        write_merchant_place(connection,transaction_id,{'provider':'google','placeId':binding['selectedPlaceId'],'method':binding['method'],'input':binding['input'],'confirmedAt':binding['confirmedAt']})
    else:
        clear_merchant_place(connection,transaction_id)


def receipt_location_preview(connection, preview, binding):
    """Show reference changes without copying transient Google display fields."""
    target = binding['target']
    old = read_merchant_place(connection,target) if target != 'new' else None
    if old and preview['before'][0]:
        preview['before'][0]['merchantPlace'] = {key:old[key] for key in ('provider','placeId','method')}
    if binding['method'] in GOOGLE_METHODS:
        preview['after'][0]['merchantPlace'] = {'provider':'google','placeId':binding['selectedPlaceId'],'method':binding['method']}
    return preview
