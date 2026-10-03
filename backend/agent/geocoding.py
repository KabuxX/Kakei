"""Permanent Mapbox address geocoding; never substitute a locality centroid."""
import math,re,time,unicodedata
import httpx
from agent.place_http import request_json,PlaceProviderError
from services.place_evidence import validate_place_evidence
from services.validation import ValidationError

from services.merchant_address import normalize_address, japanese_parts, addresses_match

def query_address(place):
    address=place['address'];fmt=place.get('address_format','original')
    if fmt=='original' or place.get('country_code')!='jp':return address
    _,address=japanese_parts(address)
    if fmt=='japanese':
        address=unicodedata.normalize('NFKC',address)
        address=re.sub(r'(\d+)[-‐−](\d+)[-‐−](\d+)(?=\s|$)',r'\1丁目\2番\3号',address)
    return address

def match_address(place,feature):
    if not isinstance(feature,dict) or not isinstance(feature.get('properties'),dict):return ['invalid_record']
    p=feature['properties'];reasons=[]
    if p.get('feature_type') not in ('address','secondary_address'):reasons.append('address_precision_unconfirmed')
    c=p.get('coordinates',{});lon,lat=c.get('longitude'),c.get('latitude')
    if not all(type(x) in (int,float) and math.isfinite(x) for x in (lon,lat)) or not -180<=lon<=180 or not -90<=lat<=90:reasons.append('invalid_coordinates')
    if c.get('accuracy') not in ('rooftop','parcel','point','interpolated'):reasons.append('accuracy_unconfirmed')
    code=p.get('match_code',{})
    if code is None:code={}
    if not isinstance(code,dict):return ['invalid_record']
    if code.get('confidence') not in ('exact','high') or code.get('address_number')!='matched' or any(v in ('unmatched','inferred','plausible') for k,v in code.items() if k!='confidence'):reasons.append('address_match_unconfirmed')
    context=p.get('context',{})
    if not isinstance(context,dict) or context.get('country',{}).get('country_code','').lower()!=place['country_code']:reasons.append('country_mismatch')
    matched=p.get('full_address')
    if not isinstance(matched,str) or not matched or len(matched)>500:reasons.append('address_missing');return reasons
    query_text=place['address'];actual_text=matched
    if place['country_code']=='jp':
        query_postal,query_text=japanese_parts(query_text);actual_postal,actual_text=japanese_parts(actual_text)
        postcode=context.get('postcode',{}) if isinstance(context,dict) else {}
        structured_postal=japanese_parts(str(postcode.get('name','')))[0] if isinstance(postcode,dict) else None
        postcodes={value for value in (query_postal,actual_postal,structured_postal) if value}
        if len(postcodes)>1:reasons.append('postcode_mismatch')
    query=normalize_address(query_text);actual=normalize_address(actual_text)
    if not addresses_match(query_text,actual_text):reasons.append('address_mismatch')
    if not re.search(r'\d',actual):reasons.append('address_number_missing')
    if not place.get('locality') or normalize_address(place['locality']) not in actual:reasons.append('locality_unconfirmed')
    return list(dict.fromkeys(reasons))

class MapboxGeocoder:
    def __init__(self,client=None):self.own=client is None;self.client=client or httpx.AsyncClient(follow_redirects=False)
    async def __aenter__(self):return self
    async def __aexit__(self,*args):
        if self.own:await self.client.aclose()
    async def geocode(self,place,*,timeout):
        address=query_address(place);country=place.get('country_code','')
        if not re.fullmatch('[a-z]{2}',country):return {'candidates':[],'unresolved':['country_unconfirmed']}
        if not isinstance(address,str) or not 1<=len(address)<=256 or len(re.findall(r'\w+',address))>20 or ';' in address:return {'candidates':[],'unresolved':['address_query_limit']}
        response=await request_json(self.client,'mapbox','/search/geocode/v6/forward',params={'q':address,'country':country,'language':'ja','limit':5,'autocomplete':'false','permanent':'true'},timeout=timeout)
        features=response.get('features')
        if not isinstance(features,list):raise PlaceProviderError('invalid_response')
        candidates=[];reasons=[];seen=set()
        for f in features[:5]:
            errors=match_address(place,f)
            review=place['country_code']=='jp' and errors==['address_match_unconfirmed']
            if errors and not review:reasons.extend(errors);continue
            p=f['properties'];c=p['coordinates'];coords=[c['longitude'],c['latitude']]
            identity=(normalize_address(p['full_address']),*coords)
            if identity in seen:continue
            seen.add(identity)
            code={k:v for k,v in (p.get('match_code') or {}).items() if k in ('confidence','address_number','street','postcode','place','region','locality','country','secondary_address','block','neighborhood')}
            g={'provider':'mapbox','providerId':p.get('mapbox_id',''),'queryAddress':address,'matchedAddress':p['full_address'],'featureType':p['feature_type'],'accuracy':c['accuracy'],'matchCode':code,'permanent':True,'retrievedAt':time.time()}
            if review:g['verification']='needs_confirmation'
            try:validate_place_evidence({'geocoding':g})
            except ValidationError:reasons.append('invalid_record');continue
            candidates.append({'coordinates':coords,'geocoding':g})
        if len(candidates)>1:return {'candidates':[],'unresolved':['ambiguous_address']}
        return {'candidates':candidates,'unresolved':[] if candidates else list(dict.fromkeys(reasons)) or ['address_not_found']}
