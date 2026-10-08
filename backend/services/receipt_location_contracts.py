"""User supplied identity and reference-only receipt location contracts."""
import hashlib
import json
from typing import TypedDict
from services.validation import ValidationError

STATUSES = frozenset(('needs_input', 'searching', 'needs_selection', 'resolved', 'not_found', 'unavailable'))
METHODS = frozenset(('receipt_address', 'user_address', 'google_unique', 'google_selected', 'existing_address', 'existing_google'))
REASONS = frozenset(('insufficient_identity', 'not_found', 'ambiguous', 'identity_mismatch', 'provider_configuration', 'provider_unavailable', 'budget_exceeded', 'expired', 'cancelled'))

class ReceiptLocationInput(TypedDict):
    merchant: str
    branch: str | None
    locality: str | None
    merchantAddress: str | None

class ReceiptLocationResolution(TypedDict):
    id: str
    receiptId: str
    revision: int
    input: ReceiptLocationInput
    inputFingerprint: str
    status: str
    placeIds: list[str]
    selectedPlaceId: str | None
    method: str | None
    reason: str | None
    confirmedAt: float | None
    expiresAt: float
    sourceTransactionId: str | None

def normalize_location_input(value: object) -> ReceiptLocationInput:
    if not isinstance(value, dict):
        raise ValidationError('input', '店舗情報を確認してください。')
    result = {}
    for key, limit in (('merchant', 200), ('branch', 200), ('locality', 200), ('merchantAddress', 500)):
        raw = value.get(key, '' if key == 'merchant' else None)
        if raw is None and key != 'merchant':
            result[key] = None
            continue
        if not isinstance(raw, str) or len(raw.strip()) > limit:
            raise ValidationError(key, '入力の形式と文字数を確認してください。')
        result[key] = raw.strip() if key == 'merchant' else raw.strip() or None
    return result

def location_fingerprint(value: ReceiptLocationInput) -> str:
    canonical = json.dumps(normalize_location_input(value), sort_keys=True, ensure_ascii=False, separators=(',', ':'))
    return hashlib.sha256(canonical.encode()).hexdigest()
