"""Small, bounded evidence values shared by search, storage and review."""
import ipaddress
import math
from urllib.parse import urlsplit,parse_qsl
from services.validation import ValidationError

def text(value,maximum,field):
    if not isinstance(value,str) or not value.strip() or len(value)>maximum:
        raise ValidationError(field,'出典情報の形式・長さを確認してください。')
    return value

def safe_source_url(value):
    text(value,2048,'sourceUrl')
    try:
        u=urlsplit(value);host=(u.hostname or '').lower().rstrip('.')
        if u.scheme!='https' or not host or u.username is not None or u.password is not None or any(c.isspace() or ord(c)<32 for c in value) or '\\' in value:raise ValueError()
        if host=='localhost' or host.endswith(('.localhost','.local','.internal')):raise ValueError()
        try: ip=ipaddress.ip_address(host)
        except ValueError: ip=None
        if ip is not None and not ip.is_global:raise ValueError()
        if host.isdecimal() or host.startswith('0x'):raise ValueError()
        if u.port not in (None,443):raise ValueError()
        if any(k.casefold() in ('key','apikey','api_key','access_token','token','authorization') for k,v in parse_qsl(u.query)):raise ValueError()
    except ValueError:raise ValidationError('sourceUrl','公開HTTPSの出典URLが必要です。') from None
    return value

def timestamp(value):
    if type(value) not in (float,int) or not math.isfinite(value) or value<0:raise ValidationError('retrievedAt','取得日時が不正です。')

def validate_sources(sources, *, maximum=3):
    if not isinstance(sources,list) or len(sources)>maximum:raise ValidationError('sources','出典件数が不正です。')
    ids=set()
    for s in sources:
        if not isinstance(s,dict) or set(s)!={'id','title','url','kind','retrievedAt'}:raise ValidationError('sources','出典の形式が不正です。')
        text(s['id'],100,'sourceId');text(s['title'],200,'title');safe_source_url(s['url']);timestamp(s['retrievedAt'])
        if s['id'] in ids or s['kind'] not in ('official','directory','other','unknown'):raise ValidationError('sources','出典の識別子・種類が不正です。')
        ids.add(s['id'])

def validate_place_evidence(place):
    if 'coordinateEvidence' in place:
        from services.coordinate_evidence import validate_coordinate_evidence
        validate_coordinate_evidence(place)
        return
    if 'sources' in place:validate_sources(place['sources'])
    if 'geocoding' not in place:return
    g=place['geocoding']
    fields={'provider','providerId','queryAddress','matchedAddress','featureType','accuracy','matchCode','permanent','retrievedAt'}
    if not isinstance(g,dict) or (not fields<=set(g) or set(g)-fields-{'verification'}) or g['provider']!='mapbox' or g['permanent'] is not True:raise ValidationError('geocoding','座標の根拠が不正です。')
    if 'verification' in g and g['verification'] not in ('needs_confirmation','user_confirmed'):raise ValidationError('verification','座標の確認状態が不正です。')
    for k,n in (('providerId',2048),('queryAddress',500),('matchedAddress',500),('featureType',40),('accuracy',40)):text(g[k],n,k)
    timestamp(g['retrievedAt'])
    allowed={'confidence','address_number','street','postcode','place','region','locality','country','secondary_address','block','neighborhood'}
    if not isinstance(g['matchCode'],dict) or set(g['matchCode'])-allowed or any(not isinstance(v,str) or len(v)>40 for v in g['matchCode'].values()):raise ValidationError('matchCode','住所の照合情報が不正です。')
