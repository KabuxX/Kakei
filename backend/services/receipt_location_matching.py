"""Match ephemeral Google candidates and return reference-only receipt results."""
import re
import unicodedata
from agent.google_places import GoogleCandidate
from services.google_place_resolution import BRANDS, address_core, normalize_name
from services.merchant_address import japanese_parts
from services.receipt_location_contracts import ReceiptLocationInput

_NON_STORE_TYPES = frozenset(('street_address', 'premise', 'subpremise', 'locality',
                            'political', 'postal_code', 'route', 'sublocality',
                            'sublocality_level_1', 'administrative_area_level_1',
                            'administrative_area_level_2', 'country'))


def _query_text(value: str | None) -> str:
    return re.sub(r'\s+', ' ', re.sub(r'[‐‑‒–—−]', '-',
                  unicodedata.normalize('NFKC', value or ''))).strip()


def receipt_query_variants(value: ReceiptLocationInput) -> list[str]:
    merchant = _query_text(value['merchant'])
    if not merchant:
        return []
    branch = _query_text(value['branch'])
    label = merchant if not branch or normalize_name(merchant).endswith(normalize_name(branch)) else f'{merchant} {branch}'
    locality = _query_text(value['locality'])
    address = _query_text(value['merchantAddress'])
    queries = [' '.join(part for part in (label, locality, address) if part)]
    if address:
        queries.append(' '.join(part for part in (label, locality, address_core(address)) if part))
    return list(dict.fromkeys(queries))[:2]


def match_receipt_places(value: ReceiptLocationInput, candidates: list[GoogleCandidate]) -> dict:
    def result(status, ids=(), selected=None, method=None, reason=None):
        return dict(status=status, placeIds=list(ids), selectedPlaceId=selected, method=method, reason=reason)

    merchant = normalize_name(value['merchant'])
    if not merchant:
        return result('needs_input', reason='insufficient_identity')
    branch = normalize_name(value['branch'] or '')
    expected = merchant if not branch or merchant.endswith(branch) else merchant + branch
    brand_only = not branch and merchant in BRANDS
    # A brand suffix may be a brand spelling variation, not a branch.
    specific = bool(branch or value['locality'] or value['merchantAddress'])
    ids = []
    prefix_only = False
    for candidate in candidates:
        actual = normalize_name(candidate.display_name)
        prefix_match = not branch and actual != expected and actual.startswith(merchant)
        if actual != expected and not prefix_match:
            continue
        if not candidate.formatted_address.strip() or not candidate.types or all(t in _NON_STORE_TYPES for t in candidate.types):
            continue
        if value['merchantAddress']:
            expected_postal, _ = japanese_parts(value['merchantAddress'])
            actual_postal, _ = japanese_parts(candidate.formatted_address)
            if expected_postal and actual_postal and expected_postal != actual_postal:
                continue
            if address_core(value['merchantAddress']) != address_core(candidate.formatted_address):
                continue
        if value['locality'] and normalize_name(value['locality']) not in normalize_name(candidate.formatted_address):
            continue
        prefix_only = prefix_only or prefix_match
        if candidate.place_id not in ids:
            ids.append(candidate.place_id)
    if not ids:
        return result('not_found', reason='identity_mismatch' if candidates else 'not_found')
    if brand_only or prefix_only or not specific:
        return result('needs_selection', ids[:10], reason='insufficient_identity')
    if len(ids) > 1:
        return result('needs_selection', ids[:10], reason='ambiguous')
    return result('resolved', ids, ids[0], 'google_unique')
