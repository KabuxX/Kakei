"""Geoapify forward geocoding. Candidate coordinates stay on the server."""
import json, math, os, uuid
from urllib.parse import urlsplit, urlunsplit
import httpx
from api.http import HTTPFailure
from services.validation import ValidationError

def search_places(query, *, bias=None, client=None):
    if not isinstance(query,str) or not 1<=len(query.strip())<=200:
        raise ValidationError('query','店舗名と地域を200文字以内で指定してください。')
    key=os.environ.get('GEOAPIFY_API_KEY','').strip()
    if not key:raise HTTPFailure(503,'places_unavailable','サーバーで GEOAPIFY_API_KEY を設定してください。既存地点や座標指定も利用できます。')
    params={'text':query.strip(),'format':'json','lang':'ja','limit':5,'apiKey':key}
    if bias is not None:
        if len(bias)!=2 or not all(type(v) in (int,float) and math.isfinite(v) for v in bias) or not -180<=bias[0]<=180 or not -90<=bias[1]<=90:
            raise ValidationError('bias','検索の中心座標が不正です。')
        params['bias']=f'proximity:{bias[0]},{bias[1]}'
    own=client is None
    client=client or httpx.Client(timeout=15,follow_redirects=False)
    try:
        with client.stream('GET','https://api.geoapify.com/v1/geocode/search',params=params,timeout=15) as response:
            response.raise_for_status();data=bytearray()
            for chunk in response.iter_bytes():
                data.extend(chunk)
                if len(data)>65536:raise ValueError('response too large')
        payload=json.loads(data)
        candidates=[]
        for item in payload.get('results',[])[:5]:
            normalized=normalize_place(item)
            if normalized['validationErrors']: continue
            candidates.append({k:normalized[k] for k in ('id','providerId','name','address','coordinates','sourceUrl','attribution')})
        return candidates
    except (httpx.HTTPError,ValueError,TypeError,AttributeError):
        raise HTTPFailure(502,'places_error','地点検索に失敗しました。地域を指定して再検索するか、座標を指定してください。') from None
    finally:
        if own:client.close()


from agent.place_http import PlaceProviderError


def normalize_place(item):
    """Preserve provider evidence; invalid coordinates remain visible for exclusion."""
    if not isinstance(item, dict):
        return {'validationErrors':['invalid_record'], 'name':'', 'address':'', 'coordinates':None}
    lon,lat=item.get('lon'),item.get('lat')
    valid=all(type(v) in (int,float) and math.isfinite(v) for v in (lon,lat)) and -180<=lon<=180 and -90<=lat<=90
    source=item.get('datasource') if isinstance(item.get('datasource'),dict) else {}
    try:
        url=urlsplit(str(source.get('url') or 'https://www.geoapify.com/'))
        safe=urlunsplit(('https',url.hostname,url.path,'','')) if url.scheme=='https' and url.hostname else 'https://www.geoapify.com/'
    except ValueError: safe='https://www.geoapify.com/'
    kind=str(item.get('result_type') or '')
    rank=item.get('rank') if isinstance(item.get('rank'),dict) else {}
    confidence=rank.get('confidence')
    return {'id':str(uuid.uuid4()), 'providerId':str(item.get('place_id') or '')[:2048],
        'name':str(item.get('name') or '')[:200], 'address':str(item.get('formatted') or '')[:500],
        'coordinates':[lon,lat] if valid else None, 'sourceUrl':safe, 'attribution':str(source.get('attribution') or 'Powered by Geoapify')[:200],
        'city':str(item.get('city') or '')[:200], 'district':str(item.get('suburb') or item.get('district') or '')[:200],
        'country_code':str(item.get('country_code') or '').lower()[:2],
        'categories':[str(x)[:80] for x in item.get('categories',[])[:20]] if isinstance(item.get('categories'),list) else [],
        'result_type':kind, 'boundary_id':str(item.get('place_id') or '')[:2048] if kind in ('city','suburb','district','state','county','country','postcode') else '',
        'confidence':confidence if type(confidence) in (int,float) and math.isfinite(confidence) else None,
        'validationErrors':[] if valid else ['invalid_coordinates']}


def spatial_params(region):
    if not region: return {}
    if region['kind']=='boundary': return {'filter': 'place:'+region['provider_id']}
    lon,lat=region['coordinates']
    return {'filter':f'circle:{lon},{lat},1000','bias':f'proximity:{lon},{lat}'}


class GeoapifyProvider:
    def __init__(self, client=None):
        self.own=client is None
        self.client=client or httpx.AsyncClient(follow_redirects=False)

    async def __aenter__(self): return self

    async def __aexit__(self,*args):
        if self.own: await self.client.aclose()

    async def _request(self,path,params,timeout,field):
        import asyncio
        key=os.environ.get('GEOAPIFY_API_KEY','').strip()
        if not key: raise PlaceProviderError('unavailable',stop_turn=True)
        params={**params,'lang':'ja','apiKey':key}
        try:
            async with asyncio.timeout(timeout):
                async with self.client.stream('GET','https://api.geoapify.com'+path,params=params,timeout=timeout,follow_redirects=False) as response:
                    if response.status_code in (401,403): raise PlaceProviderError('auth',stop_turn=True)
                    if response.status_code==429: raise PlaceProviderError('rate_limited',stop_turn=True)
                    response.raise_for_status(); data=bytearray()
                    async for chunk in response.aiter_bytes():
                        data.extend(chunk)
                        if len(data)>65536: raise PlaceProviderError('invalid_response')
            payload=json.loads(data)
            if not isinstance(payload,dict) or not isinstance(payload.get(field),list): raise PlaceProviderError('invalid_response')
            rows=payload[field][:params['limit']]
            if field=='features': rows=[r.get('properties') if isinstance(r,dict) else None for r in rows]
            return [normalize_place(r) for r in rows]
        except (TimeoutError,httpx.TimeoutException): raise PlaceProviderError('timeout') from None
        except httpx.HTTPError: raise PlaceProviderError('network') from None
        except (ValueError,TypeError,KeyError): raise PlaceProviderError('invalid_response') from None

    async def geocode(self,query,*,country_code=None,region=None,timeout):
        params={'text':query,'format':'json','limit':5,**spatial_params(region)}
        if country_code:
            params['filter']='|'.join(filter(None,(params.get('filter'),'countrycode:'+country_code)))
        return await self._request('/v1/geocode/search',params,timeout,'results')

    async def nearby(self,name,*,category,region,timeout):
        return await self._request('/v2/places',{'name':name,'categories':category,'limit':20,**spatial_params(region)},timeout,'features')
