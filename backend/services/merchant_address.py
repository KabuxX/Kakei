"""Normalization and update semantics for optional merchant addresses."""


def normalize_merchant_address(value: object) -> str | None:
    from services.validation import ValidationError
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValidationError('merchantAddress', '住所は文字列で入力してください。')
    value = value.replace('\r\n', '\n').replace('\r', '\n').strip()
    if len(value) > 500:
        raise ValidationError('merchantAddress', '住所は500文字以内で入力してください。')
    return value or None


def resolve_updated_merchant_address(old: dict, draft: dict) -> str | None:
    from services.validation import ValidationError
    if draft.get('type') != 'expense':
        return None
    if 'merchantAddress' in draft:
        return normalize_merchant_address(draft['merchantAddress'])
    if old.get('merchantAddress') and old.get('merchant') != draft.get('merchant'):
        raise ValidationError('merchantAddress', '店舗変更時は住所を確認して指定してください。')
    return old.get('merchantAddress')
