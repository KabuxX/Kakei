import copy
import sys
import tempfile
import unittest
from pathlib import Path
from urllib.parse import quote
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient
from api.app import create_app
from services.agent_changes import read_state
from test_merchant_address import DRAFT

class AddressAPITests(unittest.TestCase):
    def setUp(self):
        t=tempfile.TemporaryDirectory();self.addCleanup(t.cleanup);root=Path(t.name)
        self.app=create_app(root/'db',root);self.store=self.app.state.store
        self.client=TestClient(self.app,base_url='http://localhost:8765',headers={'Origin':'http://localhost:8765'})
        self.addCleanup(self.client.close)
        self.store.initialize([{**DRAFT,'id':'a/b %日本語','merchantAddress':'福岡市中央区天神2-11-3'}, {**DRAFT,'id':'other','merchantAddress':'福岡市中央区天神2-11-3'}])
        self.path='/api/transaction-addresses/'+quote('a/b %日本語',safe='')
        place={'name':'店舗','address':'福岡市中央区天神2-11-3','coordinates':[130.4,33.59],'placeEvidence':'legacy','sourceUrl':'https://example.com'}
        self.store.sync_trajectory({'places':{'p':place},'days':[{'date':'2026-10-01','events':[{'id':i,'placeId':'p','transactionId':tx,'time':'12:00' if i=='e' else '13:00','timeEvidence':'legacy'} for i,tx in [('e','a/b %日本語'),('f','other')]],'legs':[{'fromEventId':'e','toEventId':'f','modeHint':'walk','modeEvidence':'legacy'}]}]})

    def test_address_context_deduplicates_by_id(self):
        response=self.client.get(self.path)
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.json()['address']['places'][0]['status'],'matched')
        self.assertEqual(len(self.client.get('/api/transaction-addresses').json()['addresses']),2)
        self.assertEqual(self.client.get('/api/transaction-addresses/missing').status_code,404)

    def test_patch_is_atomic_and_preserves_other_fields(self):
        before=self.store.get_transaction('a/b %日本語')
        body={'merchantAddress':'住所B','expected':{'merchant':'店','merchantAddress':before['merchantAddress']}}
        response=self.client.patch(self.path,json=body)
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.json()['transaction'],{**before,'merchantAddress':'住所B'})
        self.assertEqual(self.client.patch(self.path,json=body).status_code,409)
        for invalid in [{'merchantAddress':'C'}, {**body,'extra':1}]:
            self.assertEqual(self.client.patch(self.path,json=invalid).status_code,400)
        tx=self.store.create_transaction({**DRAFT,'type':'income','category':'収入'})
        self.assertEqual(self.client.patch('/api/transaction-addresses/'+tx['id'],json=body).status_code,400)
        self.assertEqual(self.client.patch('/api/transaction-addresses/missing',json=body).status_code,404)
        with self.store._connection() as c:c.execute('UPDATE transactions SET merchant=NULL,payment_method=NULL WHERE id=?',('other',))
        self.assertEqual(self.client.patch('/api/transaction-addresses/other',json={'merchantAddress':'旧記録住所','expected':{'merchant':None,'merchantAddress':before['merchantAddress']}}).status_code,200)

    def test_shared_place_review_is_per_transaction(self):
        raw=copy.deepcopy(self.store.get_trajectory_day('2026-10-01'))
        self.client.patch(self.path,json={'merchantAddress':'別の住所','expected':{'merchant':'店','merchantAddress':'福岡市中央区天神2-11-3'}})
        result=self.client.get('/api/trajectory/2026-10-01').json()
        self.assertEqual([e['locationStatus'] for e in result['days'][0]['events']],['needs_review','matched'])
        self.assertEqual(result['places'],raw['places'])
        with self.store._connection() as c:
            self.assertNotIn('locationStatus',read_state(c)['timeline']['days'][0]['events'][0])

    def test_address_matching_is_conservative(self):
        from services.merchant_address import addresses_match,location_status
        self.assertTrue(addresses_match('〒810-0001 福岡市中央区天神2-11-3','日本, 〒810-0001 福岡市中央区天神２丁目１１番３号'))
        self.assertFalse(addresses_match('天神2-11-3','天神2-11-30'))
        self.assertFalse(addresses_match('〒810-0001 天神2-11-3','〒810-0002 天神2-11-3'))
        self.assertEqual(location_status(None,'住所'),'trajectory_only')
        self.assertEqual(location_status('住所',None),'needs_review')
