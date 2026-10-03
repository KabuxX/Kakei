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
    params={'text':query.strip(),'format':'json','limit':5,'apiKey':key}
    if bias is not None:
        if len(bias)!=2 or not all(type(v) in (int,float) and math.isfinite(v) for v in bias) or not -180<=bias[0]<=180 or not -90<=bias[1]<=90:
            raise ValidationError('bias','検索の中心座標が不正です。')
        params['bias']=f'proximity:{bias[0]},{bias[1]}'
    own=client is None
    client=client or httpx.Client(timeout=5,follow_redirects=False)
    try:
        with client.stream('GET','https://api.geoapify.com/v1/geocode/search',params=params,timeout=5) as response:
            response.raise_for_status();data=bytearray()
            for chunk in response.iter_bytes():
                data.extend(chunk)
                if len(data)>65536:raise ValueError('response too large')
        payload=json.loads(data)
        candidates=[]
        for item in payload.get('results',[])[:5]:
            lon,lat=item.get('lon'),item.get('lat')
            if not all(type(v) in (int,float) and math.isfinite(v) for v in (lon,lat)) or not -180<=lon<=180 or not -90<=lat<=90:continue
            source=item.get('datasource') or {}
            url=urlsplit(source.get('url') or 'https://www.geoapify.com/')
            source_url=urlunsplit((url.scheme,url.netloc,url.path,'','')) if url.scheme=='https' and url.netloc else 'https://www.geoapify.com/'
            candidates.append({'id':str(uuid.uuid4()),'providerId':str(item.get('place_id','')),'name':str(item.get('name') or item.get('formatted') or query)[:200],
                'address':str(item.get('formatted') or query)[:500],'coordinates':[lon,lat],'sourceUrl':source_url,
                'attribution':str(source.get('attribution') or 'Powered by Geoapify')[:500]})
        return candidates
    except (httpx.HTTPError,ValueError,TypeError,AttributeError):
        raise HTTPFailure(502,'places_error','地点検索に失敗しました。地域を指定して再検索するか、座標を指定してください。') from None
    finally:
        if own:client.close()
