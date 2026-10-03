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

import re
import unicodedata

def normalize_address(value):
    value=unicodedata.normalize('NFKC',value).casefold()
    digits={c:i for i,c in enumerate('〇一二三四五六七八九')}
    def number(m):
        raw=m[1]
        if '十' in raw:
            a,_,b=raw.partition('十');n=(digits.get(a,1)*10)+digits.get(b,0)
        else:n=int(''.join(str(digits[c]) for c in raw))
        return str(n)+'丁目'
    value=re.sub(r'([〇一二三四五六七八九十]+)丁目',number,value)
    value=re.sub(r'[‐‑‒–—−ー]', '-',value)
    value=re.sub(r'(?<=\d)(丁目|番地|番|号)', '-',value)
    value=re.sub(r'(?<=\d)の(?=\d)', '-',value)
    return re.sub(r'[\s,、]+','',value).strip('-')

def japanese_parts(value):
    value=unicodedata.normalize('NFKC',value).strip()
    value=re.sub(r'^(?:日本|Japan)(?:\s*[,、]\s*|\s+)', '',value,flags=re.IGNORECASE)
    match=re.match(r'^〒?\s*(\d{3})[-−‐]?(\d{4})(?:\s+|(?=[^\d])|$)',value)
    postal=''.join(match.groups()) if match else None
    return postal,value[match.end():].strip() if match else value



def addresses_match(expected: str | None, actual: str | None) -> bool:
    if not expected or not actual:
        return False
    left_postal, left = japanese_parts(expected)
    right_postal, right = japanese_parts(actual)
    if left_postal and right_postal and left_postal != right_postal:
        return False
    if normalize_address(left) == normalize_address(right):
        return True
    building = re.fullmatch(r'(.+?)\s+(?:[^\s]+(?:ビル|ビルディング|タワー|マンション|building|tower)(?:\s*\d+(?:階|f|号室))?|\d+(?:階|f|号室))', left, re.IGNORECASE)
    return bool(building and normalize_address(building[1]) == normalize_address(right))


def location_status(merchant_address, place_address) -> str:
    if not merchant_address:
        return 'trajectory_only'
    return 'matched' if addresses_match(merchant_address, place_address) else 'needs_review'
