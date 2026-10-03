"""Deterministic browser fixture; always uses disposable SQLite, never user data."""
import sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import uvicorn
from api.app import create_app

class BrowserRunner:
    def __init__(self,store):self.store=store
    async def run_turn(self, thread_id, messages, receipt_id=None, *, turn_context=None):
        if '軌跡' in messages[-1]['text']:
            candidates=[{'id':'ny','name':'同名店','address':'New York, USA','coordinates':[-73.9,40.7],'sourceUrl':'https://www.openstreetmap.org/copyright','attribution':'© OpenStreetMap contributors'}, {'id':'london','name':'同名店','address':'London, UK','coordinates':[-0.1,51.5],'sourceUrl':'https://www.openstreetmap.org/copyright','attribution':'© OpenStreetMap contributors'}]
            return {'text':'地点候補と訪問順を確認してください。','commands':[{'kind':'trajectory.create','identity':{'kind':'day','date':'2027-01-04'},'data':{'events':[{'id':'future-a','placeId':'future-shop','time':None,'timeEvidence':'unknown'},{'id':'future-b','placeId':'future-shop','time':None,'timeEvidence':'unknown'}],'legs':[{'fromEventId':'future-a','toEventId':'future-b','modeEvidence':'inferred','modeEvidenceNote':'訪問順から結んだ概算。実際の経路と手段は不明。'}]}}], 'placeCandidates':[{'placeId':'future-shop','query':'同名店','candidates':candidates}]}
        if receipt_id:
            from agent.receipt import ReceiptCandidate, receipt_review
            from services.receipt_matching import find_receipt_matches
            from db.receipt_store import ReceiptStore
            asset=ReceiptStore(self.store.db_path).get_asset(receipt_id)
            candidate=ReceiptCandidate(merchant='レシート店舗',date='2026-09-30',time='12:00',total=90,currency='JPY',payment_method='cash',items=[{'name':'商品','amount':100}],discount=10)
            if '税込' in messages[-1]['text']:
                from test_receipt_amounts import SAMPLE
                candidate=ReceiptCandidate.model_validate(SAMPLE)
            with self.store._connection() as c:matches=find_receipt_matches(c,candidate,asset['sha256'])
            return {'text':'品目と合計金額を確認してください。','commands':[],'receiptReview':{**receipt_review(candidate,matches,receipt_id),'mimeType':asset['mime_type']}}
        return {'text':'給与の追加案を作成しました。内容を確認してください。', 'commands':[{
            'kind':'transaction.create', 'identity':{}, 'data':{'title':'Agent 動作確認','date':'2026-09-30T12:00','type':'income','category':'収入','amount':12345}}]}

if __name__ == '__main__':
    with tempfile.TemporaryDirectory(prefix='kakei-agent-browser-') as directory:
        app = create_app(Path(directory)/'test.sqlite3', Path(__file__).resolve().parents[2]/'front/dist', port=8767, runner_factory=lambda store: BrowserRunner(store))
        uvicorn.run(app, host='127.0.0.1', port=8767, log_level='warning')
