"""Location evidence and conservative branch matching; no inferred coordinates."""
import math
import re
import unicodedata
import uuid
from datetime import date
from services.validation import ValidationError
from services.merchant_address import normalize_merchant_address, addresses_match
from services.agent_changes import read_state
from db.store import TrajectoryNotFound

ISO_COUNTRIES=frozenset('ad ae af ag ai al am ao aq ar as at au aw ax az ba bb bd be bf bg bh bi bj bl bm bn bo bq br bs bt bv bw by bz ca cc cd cf cg ch ci ck cl cm cn co cr cu cv cw cx cy cz de dj dk dm do dz ec ee eg eh er es et fi fj fk fm fo fr ga gb gd ge gf gg gh gi gl gm gn gp gq gr gs gt gu gw gy hk hm hn hr ht hu id ie il im in io iq ir is it je jm jo jp ke kg kh ki km kn kp kr kw ky kz la lb lc li lk lr ls lt lu lv ly ma mc md me mf mg mh mk ml mm mn mo mp mq mr ms mt mu mv mw mx my mz na nc ne nf ng ni nl no np nr nu nz om pa pe pf pg ph pk pl pm pn pr ps pt pw py qa re ro rs ru rw sa sb sc sd se sg sh si sj sk sl sm sn so sr ss st sv sx sy sz tc td tf tg th tj tk tl tm tn to tr tt tv tw tz ua ug um us uy uz va vc ve vg vi vn vu wf ws ye yt za zm zw'.split())


def normalize_text(value):
    return ' '.join(unicodedata.normalize('NFKC',value).casefold().split())


def compact(value): return normalize_text(value or '').replace(' ','')


def user_address_pair(message, name, address):
    """Accept explicit adjacent pairs; co-occurrence cannot establish identity."""
    body=normalize_text(message);name=normalize_text(name);address=normalize_text(address)
    for mention in re.finditer(re.escape(name),body):
        start=body.find(address,mention.end())
        if start<0:continue
        gap=body[mention.end():start]
        gap=re.sub(r'〒?\d{3}[-−‐]\d{4}', '',gap)
        gap=re.sub(r'(?:の)?(?:住所|所在地)(?:は|が)?|address|日本|japan', '',gap)
        if not re.fullmatch(r'[\s*_|｜:：—–\-()（）・,、]*',gap):continue
        tail=re.split(r'[。.!?！？\n]',body[start+len(address):],maxsplit=1)[0]
        if re.search(r'では(?:なく|ない|ありません)|じゃ(?:なく|ない)|でない|(?:未確認|推定|未確定|不明)|not\b',tail):continue
        return True
    return False


def coordinates_valid(coords):
    return isinstance(coords,(list,tuple)) and len(coords)==2 and all(type(v) in (int,float) and math.isfinite(v) for v in coords) and -180<=coords[0]<=180 and -90<=coords[1]<=90


def distance(a,b):
    lon1,lat1,lon2,lat2=map(math.radians,(*a,*b))
    h=math.sin((lat2-lat1)/2)**2+math.cos(lat1)*math.cos(lat2)*math.sin((lon2-lon1)/2)**2
    return 6371000*2*math.asin(min(1,math.sqrt(h)))


class EvidenceResolver:
    def __init__(self,store,searches,thread_id,messages):
        self.store,self.searches,self.thread_id,self.messages=store,searches,thread_id,messages

    def resolve(self,request):
        request={k:v for k,v in request.items() if v is not None}
        for key in ('query','brand','branch','locality','landmark','country_code'):
            if key not in request: continue
            val=request[key]
            if not isinstance(val,str) or not 1<=len(val.strip())<=200: raise ValidationError(key,'店舗名・地域は200文字以内で指定してください。')
            request[key]=normalize_text(val)
        if 'address' in request:
            request['address']=normalize_merchant_address(request['address'])
            if request['address'] is None: request.pop('address')
        if 'visit_date' in request:
            value=request['visit_date']
            try:
                if not isinstance(value,str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}',value):raise ValueError()
                date.fromisoformat(value)
            except ValueError:raise ValidationError('visit_date','訪問日はYYYY-MM-DDの実在する日付で指定してください。') from None
        if not isinstance(request.get('query'),str): raise ValidationError('query','検索語が必要です。')
        if not isinstance(request.get('place_id'),str) or not 1<=len(request['place_id'])<=100: raise ValidationError('placeId','仮地点IDが必要です。')
        if request.get('country_code') and request['country_code'] not in ISO_COUNTRIES: raise ValidationError('country_code','国コードが不正です。')
        fmt=request.setdefault('address_format','original')
        if fmt not in ('original','without_postcode','japanese'):raise ValidationError('address_format','住所の検索形式が不正です。')
        evidence=request.get('evidence',[])
        if not isinstance(evidence,list) or len(evidence)>12: raise ValidationError('evidence','検索の根拠を確認してください。')
        with self.store._connection() as c: state=read_state(c)
        users={m.get('id'):m.get('text','') for m in self.messages if m.get('role')=='user'}
        values={}; region=None; saved_region_data=None;address_stores=[]
        for e in evidence:
            if not isinstance(e,dict) or set(e)!={'field','source','source_id','value'} or e['field'] not in ('brand','branch','locality','landmark','country_code','address','visit_date') or not all(isinstance(v,str) for v in e.values()):
                raise ValidationError('evidence','根拠の形式が不正です。')
            source=e['source']; sid=e['source_id']; value=normalize_merchant_address(e['value']) if e['field']=='address' else normalize_text(e['value'])
            if not value or len(value)>(500 if e['field']=='address' else 200): raise ValidationError('evidence','根拠が空か長すぎます。')
            if source=='user_message': data=users.get(sid)
            elif source=='transaction': data=state['transactions'].get(sid)
            elif source=='saved_place': data=state['timeline']['places'].get(sid)
            elif source=='search':
                try: data=self.searches.get(self.thread_id,sid)
                except TrajectoryNotFound: raise ValidationError('evidence','この会話の検索記録がありません。') from None
            else: data=None
            if data is None: raise ValidationError('evidence','参照先がありません。')
            def strings(d):
                if isinstance(d,str): return [d]
                if isinstance(d,dict): return [s for v in d.values() for s in strings(v)]
                if isinstance(d,list): return [s for v in d for s in strings(v)]
                return []
            if e['field']=='address' and source=='transaction' and normalize_merchant_address(data.get('merchantAddress'))!=value:
                raise ValidationError('evidence','取引に保存された住所と引用が一致しません。')
            if e['field']=='visit_date':
                def dates(s):
                    normalized=normalize_text(s)
                    return {f'{int(y):04d}-{int(m):02d}-{int(d):02d}' for y,m,d in re.findall(r'(?<!\d)(\d{4})(?:年|-|/)(\d{1,2})(?:月|-|/)(\d{1,2})(?:日)?(?!\d)',normalized)}
                supported=value in dates(data.get('date','')) if source=='transaction' else any(value in dates(s) for s in strings(data))
            else:supported=any(compact(value) in compact(s) for s in strings(data))
            if not supported:raise ValidationError('evidence','引用された根拠が一致しません。')
            if e['field']=='address':
                candidates=[]
                if source=='transaction':candidates=[{'name':data.get('merchant'),'address':data.get('merchantAddress'),'sources':[]}]
                elif source=='saved_place':candidates=[data]
                elif source=='user_message' and user_address_pair(data,request['query'],value):candidates=[{'name':request['query'],'address':value,'sources':[]}]
                elif source=='search':candidates=data.get('result',{}).get('candidates',[])+data.get('result',{}).get('unlocatedCandidates',[])
                for candidate in candidates:
                    name=candidate.get('name') or ''
                    if addresses_match(value,candidate.get('address')) and compact(request.get('brand') or request['query']) in compact(name) and (not request.get('branch') or compact(request['branch']) in compact(name)):
                        address_stores.append({'name':name,'address':value,'sources':candidate.get('sources',[]),'country_code':'jp'})
            values.setdefault(e['field'],set()).add(value)
            if source=='saved_place' and coordinates_valid(data.get('coordinates')):
                region={'kind':'point','coordinates':data['coordinates'],'source_id':sid}
                saved_region_data=data
        conflicts=[key for key,items in values.items() if len(items)>1 or request.get(key) not in items]
        latest=next((m for m in reversed(self.messages) if m.get('role')=='user'),None)
        if latest:
            text=normalize_text(latest.get('text',''))
            correction=re.search(r'(今回は|ではなく|じゃなく|代わりに|this time|instead|actually)',text)
            location=re.search(r'(市|県|都|府|駅|で(?:探|検索)|の店舗|の店|\bin\s+\w)',text)
            explicit_query=re.search(r'(?:市|県|都|府|駅)で(?:探|検索)|\b(?:search|look|find)\b.*\bin\s+\S+',text)
            current=[e for e in evidence if e['source']=='user_message' and e['source_id']==latest.get('id') and e['field'] in ('locality','landmark','country_code') and request.get(e['field'])==normalize_text(e['value'])]
            if ((correction and location) or explicit_query) and not current:
                conflicts.append('current_location_correction')
            for e in current:
                if re.search(re.escape(compact(e['value']))+r'(?:ではなく|じゃなく|ではない)',compact(text)):
                    conflicts.append('negated_location')
        if saved_region_data and not locality_matches(request.get('locality'),saved_region_data):
            conflicts.append('saved_region_mismatch')
        if saved_region_data and request.get('country_code') and saved_region_data.get('country_code')!=request['country_code']:
            conflicts.append('saved_country_unconfirmed')
        if conflicts:
            return {'request':request,'saved_places':[],'region':None,'category':None,'clarification':{'status':'needs_clarification','message':'地域や店舗の指定と過去の根拠が異なります。今回の店舗・地域を確認してください。'}}
        for key in ('brand','branch','landmark'):
            if request.get(key) and key not in values and compact(request[key]) not in compact(request['query']): raise ValidationError(key,'店舗名から確認できる名称か、その根拠を指定してください。')
        for key in ('locality','country_code','address','visit_date'):
            if request.get(key) and key not in values: raise ValidationError(key,'地域の根拠を指定してください。')
        saved=[{**p,'id':str(uuid.uuid4()),'savedPlaceId':sid} for sid,p in state['timeline']['places'].items()]
        name=request['query']+' '+request.get('brand','')
        category='catering.cafe' if any(word in name for word in ('コーヒー','カフェ','coffee','cafe','café')) else None
        identities={(compact(p['name']),compact(p['address'])) for p in address_stores}
        return {'request':request,'saved_places':saved,'region':region,'clarification':None,'category':category,'address_store':address_stores[0] if len(identities)==1 else None}


def locality_matches(locality, place):
    if not locality: return True
    parts=[str(place.get(k) or '') for k in ('city','district','name','address')]
    return compact(locality) in compact(' '.join(parts))


def resolve_region(places,request):
    target=compact(request.get('landmark') or request.get('locality') or '')
    stem=target.removesuffix('駅')
    matches=[]; seen=set()
    for p in places:
        if not coordinates_valid(p.get('coordinates')): continue
        if request.get('country_code') and p.get('country_code')!=request['country_code']: continue
        if not locality_matches(request.get('locality'),p): continue
        name=compact(p.get('name',''))
        if not name or not target: continue
        if request.get('landmark'):
            if name.removesuffix('駅')!=stem and not name.startswith(stem+'('): continue
        elif target not in compact(' '.join(str(p.get(k) or '') for k in ('name','city','district'))): continue
        identity=p.get('providerId') or (name,tuple(p['coordinates']))
        if identity in seen: continue
        seen.add(identity);matches.append(p)
    if len(matches)!=1:
        return {'region':None,'clarification':{'status':'needs_clarification' if matches else 'needs_region','message':'駅・地域を一つに特定できません。市区町村や住所を教えてください。'}}
    p=matches[0]
    region={k:p.get(k,'') for k in ('country_code','city','district')}
    region['source_id']=p.get('providerId') or p['id']
    if p.get('boundary_id') and not request.get('landmark'): region.update(kind='boundary',provider_id=p['boundary_id'])
    else:
        if not request.get('landmark') and p.get('result_type') in ('city','suburb','district','state','county','country'):
            return {'region':None,'clarification':{'status':'needs_region','message':'地域の境界が取得できません。駅名や住所を教えてください。'}}
        region.update(kind='point',coordinates=p['coordinates'])
    if not region['district'] and request.get('landmark'):
        suffix=re.search(r'[（(]([^()（）]+)[)）]',p.get('name',''))
        if suffix: region['district']=suffix.group(1)
    return {'region':region,'clarification':None}


def short_query(request,region):
    parts=[request.get('brand') or request['query'],region.get('city'),region.get('district')]
    return ' '.join(dict.fromkeys(p for p in parts if p))[:200]


def match_candidates(places,request,region):
    accepted=[];excluded=[];seen=set()
    brand=compact(request.get('brand') or request['query']); branch=compact(request.get('branch',''))
    for order,p in enumerate(places):
        reasons=[];notes=[];coords=p.get('coordinates')
        if not coordinates_valid(coords): reasons.append('invalid_coordinates')
        name=compact(p.get('name','')); address=compact(p.get('address',''))
        if not name or brand not in name: reasons.append('name_mismatch')
        if branch and branch not in name and name.endswith('店'): reasons.append('different_branch')
        if request.get('address') and not addresses_match(request['address'],p.get('address')): reasons.append('address_mismatch')
        if request.get('locality') and not locality_matches(request['locality'],p): reasons.append('locality_unconfirmed')
        if region:
            for key in ('country_code','city'):
                if region.get(key) and p.get(key) and compact(region[key])!=compact(p[key]): reasons.append(key+'_mismatch')
            if region['kind']=='point' and coordinates_valid(coords) and distance(coords,region['coordinates'])>1000: reasons.append('outside_region')
        if reasons:
            excluded.append({'candidate':p,'reasons':reasons});continue
        identity=p.get('providerId') or (name,address,tuple(coords))
        if identity in seen: continue
        seen.add(identity)
        region_match=bool(region and address and (region['kind']=='point' or (region.get('city') and compact(region['city'])==compact(p.get('city','')))))
        if not region_match: notes.append('region_unconfirmed')
        if branch and branch not in name: notes.append('branch_unconfirmed')
        exact=(branch in name if branch else compact(request['query'])==name) and region_match
        candidate={k:p.get(k) for k in ('id','providerId','name','address','coordinates','sourceUrl','attribution','savedPlaceId') if p.get(k) is not None}
        candidate.setdefault('sourceUrl',None);candidate.setdefault('attribution',None)
        candidate['matchReasons']=notes or ['name_and_region_match']
        rank=0 if exact else 2 if notes else 1
        meters=distance(coords,region['coordinates']) if region and region.get('coordinates') else 0
        accepted.append((rank,meters,order,candidate,exact))
    accepted.sort(key=lambda row:row[:3])
    return {'candidates':[row[3] for row in accepted[:5]],'excluded':excluded,'exact_match':any(row[4] for row in accepted),'truncated':len(accepted)>5}
