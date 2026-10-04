"""Prepare resolved visits and commit them in the caller's fenced transaction."""
import copy
import hashlib
import re
import uuid
from dataclasses import dataclass
from db.store import TrajectoryConflict
from db.trajectory_store import replace_trajectory
from db.google_place_cache import write_cached_coordinates
from services.agent_changes import canonical, read_state
from services.google_place_resolution import VisitInput, VisitResolution
from services.trajectory_mutation import _date
from services.trajectory_validation import validate_timeline

REASONS={
    'not_visit':'実店舗の訪問を示す取引ではありません。',
    'insufficient_identity':'店舗や所在地を特定する情報が不足しています。',
    'not_found':'条件に合う店舗が見つかりませんでした。',
    'ambiguous':'同名の候補が複数あり、店舗を特定できませんでした。',
    'identity_mismatch':'候補の店舗・支店または住所が記録と合いませんでした。',
    'missing_coordinates':'店舗の有効な座標を取得できませんでした。',
    'provider_unavailable':'通信エラーや利用上限により検索できませんでした。',
    'budget_exceeded':'処理時間内に検索を完了できませんでした。',
    'provider_configuration':'Google Places APIの設定を確認してください。',
    'source_conflict':'検索中に対象データが変わったため保存しませんでした。',
    'save_failed':'保存を完了できませんでした。',
}

@dataclass(frozen=True)
class PreparedCreation:
    date: str
    source_version: str
    timeline: dict
    resolutions: list[VisitResolution]
    result: dict


def state_version(state):
    return hashlib.sha256(canonical(state).encode()).hexdigest()


def result_text(result):
    counts=result['counts'];date=result['date']
    if result['status']=='failed':
        return f'{date}の軌跡を保存できませんでした。'
    if counts['saved']:
        return f'{date}の軌跡を作成しました。{counts["saved"]}件保存、{counts["existing"]}件登録済み、{counts["excluded"]}件除外。'
    return f'{date}の軌跡は変更していません。{counts["existing"]}件登録済み、{counts["excluded"]}件除外。'


class TrajectoryCreationService:
    def __init__(self,store,resolver):
        self.store,self.resolver=store,resolver

    async def prepare(self,date):
        date=_date(date)
        with self.store._connection() as connection:
            connection.execute('BEGIN')
            state=read_state(connection)
        version=state_version(state);timeline=copy.deepcopy(state['timeline'])
        records=sorted((t for t in state['transactions'].values() if t['date'][:10]==date),key=lambda t:(t['date'],t['id']))
        day=next((d for d in timeline['days'] if d['date']==date),{'date':date,'events':[],'legs':[]})
        existing={event['transactionId']:event for event in day['events'] if event.get('transactionId')}
        result={'date':date,'status':'unchanged','counts':{'saved':0,'existing':0,'excluded':0},'saved':[],'existing':[],'excluded':[]}
        record_map={t['id']:t for t in records};inputs=[]
        def entry(t):
            return {'transactionId':t['id'],'label':t.get('merchant') or t['title'],'time':t['date'][11:16], 'timeEstimated':t.get('timeEstimated',False)}
        def exclude(t,reason):
            result['excluded'].append({**entry(t),'reason':reason,'message':REASONS[reason]})
        for record in records:
            if record['id'] in existing:
                result['existing'].append({**entry(record),'eventId':existing[record['id']]['id']})
            elif record['type']!='expense' or re.search(r'オンライン(?:購入|注文|決済)|通販|ネット注文',record['title']):
                exclude(record,'not_visit')
            else:
                inputs.append(VisitInput(record['id'],record.get('merchant') or record['title'],record.get('merchantAddress')))
        resolutions=await self.resolver.resolve_many(inputs)
        new_events=[]
        for resolution in resolutions:
            record=record_map[resolution.transaction_id]
            if resolution.reason:
                exclude(record,resolution.reason)
                continue
            identifier=str(uuid.uuid5(uuid.NAMESPACE_URL,'kakei:visit:'+date+':'+record['id']))
            place_id='google:'+resolution.provider_place_id
            timeline['places'].setdefault(place_id,{'name':record.get('merchant') or record['title'], 'address':record.get('merchantAddress'),
                'sourceUrl':None,'placeEvidence':'google_places','provider':'google','providerPlaceId':resolution.provider_place_id})
            event={'id':identifier,'time':record['date'][11:16],'timeEvidence':'estimated' if record.get('timeEstimated') else 'exact',
                   'placeId':place_id,'transactionId':record['id']}
            if record.get('timeEstimated'):
                event['timeEvidenceNote']='取引に設定された推定時刻。実際の訪問時刻は未確認。'
            new_events.append(event)
            result['saved'].append({**entry(record),'eventId':identifier})
        if new_events:
            old_order={e['id']:i for i,e in enumerate(day['events'])}
            old_legs={(l['fromEventId'],l['toEventId']):l for l in day['legs']}
            day['events']=sorted(day['events']+new_events,key=lambda e:(e['time'] is None,e['time'] or '',
                0 if e['id'] in old_order else 1,old_order.get(e['id'],0),e.get('transactionId','')))
            day['legs']=[copy.deepcopy(old_legs.get((a['id'],b['id']),{'fromEventId':a['id'],'toEventId':b['id'],
                'modeEvidence':'inferred','modeEvidenceNote':'訪問順から結んだ概算。実際の経路と移動手段は不明。'}))
                for a,b in zip(day['events'],day['events'][1:])]
            if not any(d['date']==date for d in timeline['days']):
                timeline['days'].append(day)
                timeline['days'].sort(key=lambda d:d['date'])
            validate_timeline(timeline,require_complete=False)
        for key in ('saved','existing','excluded'):
            result['counts'][key]=len(result[key])
        if new_events:
            result['status']='partial' if result['excluded'] else 'created'
        return PreparedCreation(date,version,timeline,resolutions,result)


def apply_creation(connection,prepared,*,now):
    if not isinstance(prepared,PreparedCreation) or state_version(read_state(connection))!=prepared.source_version:
        raise TrajectoryConflict('検索中に対象データが変わりました。')
    result=copy.deepcopy(prepared.result)
    if result['counts']['saved']:
        validate_timeline(prepared.timeline,require_complete=False)
        replace_trajectory(connection,prepared.timeline)
        for resolution in prepared.resolutions:
            if resolution.provider_place_id and resolution.coordinates is not None:
                write_cached_coordinates(connection,resolution.provider_place_id,resolution.coordinates,resolution.obtained_at)
        connection.execute("INSERT OR REPLACE INTO meta (key,value) VALUES ('trajectory_seeded','1')")
        connection.execute("INSERT OR REPLACE INTO meta (key,value) VALUES ('trajectory_modified','1')")
    return result
