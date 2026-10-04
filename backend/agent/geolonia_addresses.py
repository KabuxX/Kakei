"""Conservative address retries: preserve the grounded residential numbers."""
import re
import unicodedata
from services.merchant_address import japanese_parts, addresses_match
from services.geolonia_evidence import address_agrees
from agent.place_matching import coordinates_valid


def eligible_address(address: str, country_code: str | None) -> bool:
    if not isinstance(address,str) or not address.strip() or country_code not in (None,'jp'):
        return False
    value=unicodedata.normalize('NFKC',address)
    return bool(re.search(r'[一-龯々]+(?:市|区|郡|町|村)',value))


def address_variants(address: str, *, grounded_prefixes: list[str]) -> list[dict]:
    result=[];seen=set();strategies=[]
    def add(value,strategy):
        if strategy not in strategies:strategies.append(strategy)
        value=value.strip()
        if value and value not in seen and len(result)<6:
            seen.add(value);result.append({'address':value,'strategies':list(strategies)})
        return value
    current=add(address,'original')
    _,current=japanese_parts(current)
    current=add(current,'without_postcode_country')
    current=unicodedata.normalize('NFKC',current)
    current=re.sub(r'(?<=\d)[‐‑‒–—−ー](?=\d)','-',current)
    current=add(' '.join(current.split()),'nfkc_spacing')
    # Canonicalize only the numeric address portion; do not touch town names.
    numeric=re.sub(r'(?<=\d)(丁目|番地|番|号)(?=\d|\s|$)','-',current)
    numeric=re.sub(r'-(?=\s|$)','',numeric)
    current=add(numeric,'number_notation')
    building=re.fullmatch(r'(.+?\d)\s+(?:[^\s]+(?:ビル|ビルディング|タワー|マンション|building|tower)(?:\s*\d+(?:階|f|号室))?|\d+(?:階|f|号室))',current,re.IGNORECASE)
    if building:
        current=add(building[1],'without_building')
    for prefix in grounded_prefixes:
        if isinstance(prefix,str) and re.fullmatch(r'[一-龯々]+(?:都|道|府|県)(?:[一-龯々]+(?:市|区|郡|町|村))*',prefix) and not current.startswith(prefix):
            add(prefix+current,'grounded_prefix')
    return result


def match_reasons(original: str, variant: dict, match: dict) -> list[str]:
    reasons=[]
    if not isinstance(match,dict):return ['geolonia_invalid_response']
    point=match.get('point')
    if type(match.get('level')) is not int or match['level']!=8 or not isinstance(point,dict) or type(point.get('level')) is not int or point['level']!=8:
        reasons.append('address_precision_unconfirmed')
    if not isinstance(point,dict) or not coordinates_valid([point.get('lng'),point.get('lat')]):
        reasons.append('position_unverified')
    components={k:match.get(k) for k in ('pref','city','town','addr')}
    if any(not isinstance(v,str) or not v for v in components.values()):
        reasons.append('address_match_unconfirmed')
    else:
        matched=''.join(components.values())
        if not address_agrees(original,variant['address'],matched,components):reasons.append('address_mismatch')
    other=match.get('other','')
    if other and (not isinstance(other,str) or re.search(r'^[\s-]*\d',other) or not addresses_match(original,''.join(v for v in components.values() if isinstance(v,str)))):
        reasons.append('address_match_unconfirmed')
    return list(dict.fromkeys(reasons))
