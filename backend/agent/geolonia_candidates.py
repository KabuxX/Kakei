"""Turn validated dataset matches into immutable review candidates."""
import copy
import json
from services.coordinate_evidence import validate_coordinate_evidence
from services.validation import ValidationError
from agent.geolonia_addresses import match_reasons


def candidate_from_match(store: dict, result: dict) -> dict | None:
    if result.get('status')!='matched':return None
    try:
        match=result['match'];variant=result['matchedVariant'];proof=result['proof']
        if match_reasons(result['originalAddress'],variant,match):return None
        sources=copy.deepcopy(store.get('sources',[]))
        existing={s['url']:s['id'] for s in sources};mapping={}
        fetches=copy.deepcopy(proof['fetches'])
        for f in fetches:
            sid=existing.get(f['url'])
            if sid is None:
                sid='geolonia:'+str(len(sources)+1);existing[f['url']]=sid
                sources.append({'id':sid,'title':'Geolonia japanese-addresses-v2','url':f['url'],'kind':'directory','retrievedAt':f['retrievedAt']})
            mapping[f['sourceId']]=sid;f['sourceId']=sid
        observation=copy.deepcopy(proof['observation']);observation['sourceId']=mapping[observation['sourceId']]
        components={k:match[k] for k in ('pref','city','town','addr')}
        address_match={'provider':'geolonia','libraryVersion':result['libraryVersion'],'originalAddress':result['originalAddress'],'queryAddress':variant['address'],'matchedAddress':''.join(components.values()),'strategies':variant['strategies'],'level':match['level'],'pointLevel':match['point']['level'],'components':components,'record':match['record'],'fetches':fetches}
        candidate={'name':store['name'],'address':store['address'],'country_code':'jp','coordinates':[match['point']['lng'],match['point']['lat']],'sourceUrl':store.get('sourceUrl') or sources[0]['url'],'sources':sources,'attribution':'Geolonia japanese-addresses-v2 · CC BY 4.0（加工して利用）','placeEvidence':'provider','matchReasons':['store_and_address_verified'],
            'coordinateEvidence':{'version':2,'status':'address_matched','method':'geolonia_address','sourceIds':list(dict.fromkeys(f['sourceId'] for f in fetches)),'retrievedAt':max(f['retrievedAt'] for f in fetches),'precision':'address','note':'住所に対応する座標。番地・住居番号まで照合。店舗の入口は未確認。','verification':'needs_confirmation','observations':[observation],'addressMatch':address_match}}
        validate_coordinate_evidence(candidate)
        if len(json.dumps(candidate,ensure_ascii=False).encode())>8192:return None
        return candidate
    except (KeyError,ValueError,TypeError,AttributeError,ValidationError):return None
