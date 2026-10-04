"""Validation for dataset address coordinates, distinct from store pins."""
import json
import re
from urllib.parse import urlsplit
from services.place_evidence import text, timestamp, validate_sources
from services.merchant_address import addresses_match, normalize_address, japanese_parts

DATASET_HOST = 'japanese-addresses-v2.geoloniamaps.com'


def dataset_url(value):
    from services.place_evidence import safe_source_url
    safe_source_url(value)
    u = urlsplit(value)
    return u.hostname == DATASET_HOST and u.path.startswith('/api/ja') and (not u.query or re.fullmatch(r'v=\d+',u.query)) and not u.fragment


def address_agrees(original, query, matched, components):
    if not addresses_match(query, matched):
        return False
    if addresses_match(original, query):
        return True
    # Only complete administrative components may precede the grounded input.
    _, base = japanese_parts(original)
    normalized = normalize_address(base)
    prefixes = [components['pref'], components['pref'] + components['city']]
    return any(addresses_match(prefix + base, query) for prefix in prefixes) and bool(normalized)


def validate_geolonia_evidence(place: dict) -> None:
    from services.coordinate_evidence import invalid, valid_coordinates, references
    e = place.get('coordinateEvidence')
    required = {'version','status','method','sourceIds','retrievedAt','precision','note','verification','observations','addressMatch'}
    if not isinstance(e, dict) or set(e) != required or 'geocoding' in place:
        invalid()
    if type(e['version']) is not int or e['version'] != 2 or (e['status'],e['method'],e['precision']) != ('address_matched','geolonia_address','address'):
        invalid()
    if e['verification'] not in ('needs_confirmation','user_confirmed'):
        invalid()
    validate_sources(place.get('sources'), maximum=6)
    sources = {s['id']: s for s in place['sources']}
    refs = references(e['sourceIds'], set(sources))
    timestamp(e['retrievedAt']); text(e['note'],500,'note')
    if not valid_coordinates(place.get('coordinates')):
        invalid()
    m = e['addressMatch']
    fields = {'provider','libraryVersion','originalAddress','queryAddress','matchedAddress','strategies','level','pointLevel','components','record','fetches'}
    if not isinstance(m,dict) or set(m) != fields or m['provider'] != 'geolonia':
        invalid()
    if not isinstance(m['libraryVersion'],str) or not re.fullmatch(r'\d+\.\d+\.\d+',m['libraryVersion']):
        invalid()
    if any(type(m[k]) is not int or m[k] != 8 for k in ('level','pointLevel')):
        invalid()
    for key in ('originalAddress','queryAddress','matchedAddress'):
        text(m[key],500,key)
    strategies = m['strategies']
    if not isinstance(strategies,list) or not 1 <= len(strategies) <= 6 or any(s not in ('original','without_postcode_country','nfkc_spacing','number_notation','without_building','grounded_prefix') for s in strategies):
        invalid()
    components = m['components']
    if not isinstance(components,dict) or set(components) != {'pref','city','town','addr'}:
        invalid()
    for key in components:
        text(components[key],200,key)
    if ''.join(components[k] for k in ('pref','city','town','addr')) != m['matchedAddress'] or not address_agrees(m['originalAddress'],m['queryAddress'],m['matchedAddress'],components):
        invalid()
    if not addresses_match(place.get('address'),m['originalAddress']):
        invalid()
    record = m['record']
    if not isinstance(record,dict) or set(record) != {'kind','fields'} or record['kind'] not in ('rsdt','chiban') or not isinstance(record['fields'],dict):
        invalid()
    f = record['fields']
    number_fields = ('blk_num','rsdt_num','rsdt_num2') if record['kind']=='rsdt' else ('prc_num1','prc_num2','prc_num3')
    mandatory = 'rsdt_num' if record['kind']=='rsdt' else 'prc_num1'
    if mandatory not in f or set(f) - set(number_fields) - {'point'} or not valid_coordinates(f.get('point')) or f['point'] != place['coordinates']:
        invalid()
    for key in number_fields:
        if key in f: text(f[key],40,key)
    if normalize_address('-'.join(f[k] for k in number_fields if k in f)) != normalize_address(components['addr']):
        invalid()
    fetches = m['fetches']
    if not isinstance(fetches,list) or not 1 <= len(fetches) <= 4:
        invalid()
    dataset_refs = set()
    for fetch in fetches:
        if not isinstance(fetch,dict) or set(fetch) != {'sourceId','url','retrievedAt','range','sha256','updatedAt'}:
            invalid()
        sid = fetch['sourceId']
        if not isinstance(sid,str) or sid not in refs or sources[sid]['url'] != fetch['url'] or not dataset_url(fetch['url']):
            invalid()
        timestamp(fetch['retrievedAt'])
        if fetch['updatedAt'] is not None: timestamp(fetch['updatedAt'])
        if not isinstance(fetch['sha256'],str) or not re.fullmatch('[0-9a-f]{64}',fetch['sha256']):
            invalid()
        span = fetch['range']
        if span is not None and (not isinstance(span,dict) or set(span) != {'offset','length'} or type(span['offset']) is not int or span['offset'] < 0 or type(span['length']) is not int or not 1 <= span['length'] <= 8*1024*1024):
            invalid()
        dataset_refs.add(sid)
    observations = e['observations']
    if not isinstance(observations,list) or not 1 <= len(observations) <= 4:
        invalid()
    for o in observations:
        if not isinstance(o,dict) or set(o) != {'sourceId','kind','excerpt','coordinates'} or not isinstance(o['sourceId'],str) or o['sourceId'] not in dataset_refs or o['kind'] != 'geolonia_address' or o['coordinates'] != place['coordinates']:
            invalid()
        text(o['excerpt'],2048,'excerpt')
        try: observed = json.loads(o['excerpt'])
        except (ValueError,TypeError): invalid()
        if observed != {'components':components,'record':record}:
            invalid()


def rebind_geolonia_sources(evidence: dict, mapping: dict[str,str]) -> None:
    for fetch in evidence['addressMatch']['fetches']:
        fetch['sourceId'] = mapping.get(fetch['sourceId'],fetch['sourceId'])
