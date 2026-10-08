"""Real API with disposable SQLite and synthetic clients; no external requests."""
import sys, tempfile, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import uvicorn
from agent.receipt import ReceiptCandidate, receipt_review
from agent.google_places import GoogleCandidate, GooglePlacesError
from google_places_fixtures import place
from services.receipt_location import ReceiptLocationService
from db.receipt_store import ReceiptStore
from api.app import create_app

class FixedGoogle:
    fail_display = False
    async def __aenter__(self): return self
    async def __aexit__(self, *args): pass
    async def search_text(self, query, **kwargs):
        ids = ['fixture-a','fixture-b'] if '曖昧' in query else ['fixture-retry' if '再試行' in query else 'fixture-unique']
        name = '曖昧ストア' if '曖昧' in query else '再試行ストア' if '再試行' in query else '一意ストア'
        return [GoogleCandidate.from_payload(place(i,name,'架空県サンプル市1-2-3')) for i in ids]
    async def details(self, identifier):
        if identifier == 'fixture-retry' and FixedGoogle.fail_display:
            FixedGoogle.fail_display = False
            raise GooglePlacesError('unavailable','synthetic failure')
        name = '曖昧ストア' if identifier in ('fixture-a','fixture-b') else '再試行ストア' if identifier == 'fixture-retry' else '一意ストア'
        return GoogleCandidate.from_payload(place(identifier,name,'架空県サンプル市1-2-3'))

def service(store): return ReceiptLocationService(store,client_factory=FixedGoogle)
class FixedRunner:
    def __init__(self,store): self.store=store
    async def run_turn(self,thread_id,messages,receipt_id=None,*,turn_context=None):
        text=messages[-1]['text']
        name='曖昧ストア' if '曖昧' in text else '再試行ストア' if '再試行' in text else '一意ストア'
        candidate=ReceiptCandidate(merchant=name,date='2026-10-08',time='12:00',total=100,currency='JPY',payment_method='cash',items=[{'name':'商品','amount':100}])
        resolution=await service(self.store).initialize(thread_id,receipt_id,candidate,deadline=time.monotonic()+175,turn_context=turn_context)
        if '再試行' in text: FixedGoogle.fail_display=True
        asset=ReceiptStore(self.store.db_path).get_asset(receipt_id)
        return {'text':'店舗と住所を確認してください。','commands':[],'receiptReview':{**receipt_review(candidate,[],receipt_id),'mimeType':asset['mime_type'],'locationResolution':resolution}}

if __name__=='__main__':
    from agent import google_places
    google_places.GooglePlacesClient=FixedGoogle
    with tempfile.TemporaryDirectory(prefix='kakei-receipt-location-browser-') as directory:
        root=Path(__file__).resolve().parents[2]
        app=create_app(Path(directory)/'test.sqlite3',root/'front/dist',port=8768,runner_factory=FixedRunner,receipt_location_service_factory=service)
        app.state.store.initialize([])
        @app.get('/api/test/location-state')
        def state():
            records=app.state.store.list_transactions()
            with app.state.store._connection() as connection:
                count=connection.execute('SELECT COUNT(*) FROM transaction_merchant_places').fetchone()[0]
                latest=connection.execute('SELECT id FROM transactions ORDER BY rowid DESC LIMIT 1').fetchone()
            return {'transactions':len(records),'references':count,'latest':next((r for r in records if latest and r['id']==latest['id']),None)}
        # StaticFiles was registered first: put test-only inspection before the mount.
        app.router.routes.insert(0,app.router.routes.pop())
        uvicorn.run(app,host='127.0.0.1',port=8768,log_level='warning')
