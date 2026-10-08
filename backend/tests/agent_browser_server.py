"""Deterministic browser fixture; always uses disposable SQLite, never user data."""
import json, sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import uvicorn
from api.app import create_app

class BrowserGoogle:
    async def __aenter__(self): return self
    async def __aexit__(self,*args): pass
    async def search_text(self,query,**kwargs):
        from agent.google_places import GoogleCandidate
        from google_places_fixtures import place
        name=next((name for name in ('合成店舗A','合成店舗B','合成店舗C') if name in query),'合成店舗A')
        suffixes=('one','two') if name.endswith('C') else ('one',)
        return [GoogleCandidate.from_payload(place('fixture-'+name[-1]+suffix,name)) for suffix in suffixes]
    async def details(self,place_id):
        from agent.google_places import GoogleCandidate
        from google_places_fixtures import place
        return GoogleCandidate.from_payload(place(place_id,'合成表示店舗'))

class BrowserRunner:
    def __init__(self,store):self.store=store
    async def run_turn(self, thread_id, messages, receipt_id=None, *, turn_context=None):
        if '2027-04-' in messages[-1]['text']:
            from agent.runtime import AgentRunner
            from unittest.mock import patch
            with patch('agent.google_places.GooglePlacesClient',BrowserGoogle):
                return await AgentRunner(self.store).run_turn(thread_id,messages,receipt_id,turn_context=turn_context)
        if 'Geolonia座標の確認' in messages[-1]['text']:
            import copy
            from geolonia_fixtures import GEOLONIA_PLACE
            from coordinate_fixtures import PUBLISHED_PLACE
            return {'text':'住所に対応する座標と出典を確認してください。','commands':[{'kind':'trajectory.create','identity':{'kind':'day','date':'2027-03-01'},'data':{'events':[{'id':'geo-visit','time':'12:00','timeEvidence':'exact','placeId':'geo-shop'}],'legs':[]}}],
                'placeCandidates':[{'placeId':'geo-shop','query':'合成テスト店舗','candidates':[{**copy.deepcopy(GEOLONIA_PLACE),'id':'geo'},{**copy.deepcopy(PUBLISHED_PLACE),'id':'web'}],'unlocatedCandidates':[{'id':'coarse','name':'町丁目までの店舗','address':'東京都文京区本郷','sources':[],'unresolved':['address_precision_unconfirmed']}]}]}
        if '削除の動作確認' in messages[-1]['text']:
            import re
            text=messages[-1]['text']
            day=re.search(r'2027-02-0[123]',text).group()
            saved=self.store.get_trajectory_day(day)['days'][0]
            identity={'kind':'day','date':day}
            if '訪問を削除' in text:
                identity.update(kind='event',id=saved['events'][1]['id'])
            elif '移動区間を削除' in text:
                identity.update(kind='leg',fromEventId=saved['legs'][0]['fromEventId'],toEventId=saved['legs'][0]['toEventId'])
            return {'text':'削除対象と移動区間への影響を確認してください。','commands':[{'kind':'trajectory.delete','identity':identity,'data':{}}]}
        if any(term in messages[-1]['text'] for term in ('Web座標の確認','推定位置の確認')):
            import copy
            from coordinate_fixtures import PUBLISHED_PLACE,ESTIMATED_PLACE
            candidates=[{**copy.deepcopy(PUBLISHED_PLACE),'id':'published'},{**copy.deepcopy(ESTIMATED_PLACE),'id':'estimated'}]
            return {'text':'掲載座標と推定位置の根拠を確認してください。','commands':[{'kind':'trajectory.create','identity':{'kind':'day','date':'2027-01-06'},'data':{'events':[{'id':'estimated-visit','placeId':'estimated-shop','time':'12:00','timeEvidence':'exact'},{'id':'estimated-visit-2','placeId':'estimated-shop','time':'13:00','timeEvidence':'exact'}],'legs':[{'fromEventId':'estimated-visit','toEventId':'estimated-visit-2','modeEvidence':'inferred','modeEvidenceNote':'地点間を結んだ概算。'}]}}],'placeCandidates':[{'placeId':'estimated-shop','query':'店舗','candidates':candidates}]}
        if '住所の位置を修正'  in messages[-1]['text']:
            tx=next(t for t in self.store.list_transactions() if t['title']=='住所の統合確認')
            return {'text':'新しい住所と地点を確認してください。','commands':[{'kind':'trajectory.update','identity':{'kind':'day','date':'2026-10-04'},'data':{'events':[{'id':'address-visit','placeId':'corrected-address','time':'12:00','timeEvidence':'exact','transactionId':tx['id']}],'legs':[]}}], 'placeCandidates':[{'placeId':'corrected-address','query':tx['merchant'],'candidates':[{'id':'corrected-candidate','name':tx['merchant'],'address':tx['merchantAddress'],'coordinates':[130.401,33.591],'sourceUrl':'https://example.com/corrected','attribution':'ブラウザ検証データ'}]}]}
        if 'Web出典'  in messages[-1]['text']:
            from web_place_fixtures import SOURCE,PLACE
            result={'text':'店舗を確認しました [source:s1]','sources':[SOURCE],'commands':[]}
            if '軌跡' in messages[-1]['text']:
                result.update(commands=[{'kind':'trajectory.create','identity':{'kind':'day','date':'2027-01-05'},'data':{'events':[{'id':'web-event','placeId':'web-shop','time':'12:00','timeEvidence':'exact'}],'legs':[]}}],placeCandidates=[{'placeId':'web-shop','query':'店舗','candidates':[{**PLACE,'id':'web-candidate','geocoding':{**PLACE['geocoding'],'accuracy':'interpolated','verification':'needs_confirmation'}}],'unlocatedCandidates':[{'id':'unlocated','name':'住所のみ確認できた店舗','address':'福岡市中央区','sources':[SOURCE],'unresolved':['address_precision_unconfirmed']}]}])
            return result
        if '軌跡' in messages[-1]['text']:
            candidates=[{'id':'ny','name':'同名店','address':'New York, USA','coordinates':[-73.9,40.7],'sourceUrl':'https://www.openstreetmap.org/copyright','attribution':'© OpenStreetMap contributors'}, {'id':'london','name':'同名店','address':'London, UK','coordinates':[-0.1,51.5],'sourceUrl':'https://www.openstreetmap.org/copyright','attribution':'© OpenStreetMap contributors'}]
            return {'text':'地点候補と訪問順を確認してください。','commands':[{'kind':'trajectory.create','identity':{'kind':'day','date':'2027-01-04'},'data':{'events':[{'id':'future-a','placeId':'future-shop','time':None,'timeEvidence':'unknown'},{'id':'future-b','placeId':'future-shop','time':None,'timeEvidence':'unknown'}],'legs':[{'fromEventId':'future-a','toEventId':'future-b','modeEvidence':'inferred','modeEvidenceNote':'訪問順から結んだ概算。実際の経路と手段は不明。'}]}}], 'placeCandidates':[{'placeId':'future-shop','query':'同名店','candidates':candidates}]}
        if receipt_id:
            from agent.receipt import ReceiptCandidate, receipt_review
            from services.receipt_matching import find_receipt_matches
            from db.receipt_store import ReceiptStore
            asset=ReceiptStore(self.store.db_path).get_asset(receipt_id)
            candidate=ReceiptCandidate(merchant='レシート店舗',merchant_address='架空県テスト市1-1',date='2026-09-30',time='12:00',total=90,currency='JPY',payment_method='cash',items=[{'name':'商品','amount':100}],discount=10)
            if '税込' in messages[-1]['text']:
                from test_receipt_amounts import SAMPLE
                candidate=ReceiptCandidate.model_validate({**SAMPLE,'merchant_address':'東京都千代田区二番町8-8'})
            from services.receipt_location import ReceiptLocationService
            import time
            location=await ReceiptLocationService(self.store,client_factory=BrowserGoogle).initialize(thread_id,receipt_id,candidate,deadline=time.monotonic()+175,turn_context=turn_context)
            with self.store._connection() as c:matches=find_receipt_matches(c,candidate,asset['sha256'])
            return {'text':'品目と合計金額を確認してください。','commands':[],'receiptReview':{**receipt_review(candidate,matches,receipt_id),'mimeType':asset['mime_type'],'locationResolution':location}}
        return {'text':'給与の追加案を作成しました。内容を確認してください。', 'commands':[{
            'kind':'transaction.create', 'identity':{}, 'data':{'title':'Agent 動作確認','date':'2026-09-30T12:00','type':'income','category':'収入','amount':12345}}]}

if __name__ == '__main__':
    from agent import google_places
    google_places.GooglePlacesClient=BrowserGoogle
    with tempfile.TemporaryDirectory(prefix='kakei-agent-browser-') as directory:
        root = Path(__file__).resolve().parents[2]
        app = create_app(Path(directory)/'test.sqlite3', root/'front/dist', port=8767,
                         timeline_path=root/'front/src/data/september-timeline.json',
                         runner_factory=lambda store: BrowserRunner(store))
        app.state.store.initialize(json.loads((root/'front/src/data/september-transactions.json').read_text()))
        uvicorn.run(app, host='127.0.0.1', port=8767, log_level='warning')
