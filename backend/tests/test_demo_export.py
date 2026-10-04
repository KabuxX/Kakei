import sys, unittest, tempfile, sqlite3, json, hashlib, copy
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from db.store import Store
from db.agent_store import AgentStore
from demo.export_snapshot import export_demo
from demo.validate_snapshot import validate_snapshot

class DemoExportTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
  self.root=Path(self.tmp.name);self.db=self.root/'db';self.out=self.root/'demo';self.curated=self.root/'places.json';self.curated.write_text('{}')
  self.store=Store(self.db);self.store.initialize([])
  a=AgentStore(self.db);self.thread=a.create_thread();a.append_message(self.thread['id'],'m','user','原本と会話を保存')
  with self.store._connection() as c:
   c.execute("insert into receipt_assets(id,thread_id,mime_type,sha256,page_count,data,created_at,expires_at) values(?,?,?,?,?,?,?,?)",('receipt-1',self.thread['id'],'image/png',hashlib.sha256(b'original').hexdigest(),1,b'original',1,2))
   c.execute("update agent_messages set metadata_json=?",(json.dumps({'privateLog':'secret','sources':[]}),))
 def dump(self):
  with sqlite3.connect(self.db) as c:return '\n'.join(c.iterdump())
 def export(self):
  export_demo(self.db,self.out,self.curated,'2026-10-05T00:00:00Z');return json.loads((self.out/'data/snapshot.json').read_text())
 def test_keeps_expired_original_and_user_text_without_mutating_db(self):
  before=self.dump();s=self.export();self.assertEqual(self.dump(),before)
  self.assertEqual(s['threads'][0]['messages'][0]['text'],'原本と会話を保存');self.assertNotIn('privateLog',json.dumps(s))
  self.assertEqual((self.out/'public'/s['receipts']['receipt-1']['path']).read_bytes(),b'original')
 def test_rejects_missing_or_corrupted_original(self):
  s=self.export();p=self.out/'public'/s['receipts']['receipt-1']['path'];p.write_bytes(b'bad')
  with self.assertRaises(ValueError):validate_snapshot(s,self.out/'public')
  p.unlink()
  with self.assertRaises(ValueError):validate_snapshot(s,self.out/'public')
 def test_rejects_invalid_budget_and_references(self):
  s=self.export();s['categories']['食費']=-1
  with self.assertRaises(ValueError):validate_snapshot(s,self.out/'public')
  s=self.export();s['timeline']={'places':{'p':{'name':'p','coordinates':[139,35]}},'days':[{'date':'2026-10-01','events':[{'id':'e','placeId':'p','transactionId':'missing'}],'legs':[]}]}
  with self.assertRaises(ValueError):validate_snapshot(s,self.out/'public')
  s['timeline']['days'][0]['events'][0].pop('transactionId');s['timeline']['days'][0]['events']*=2
  with self.assertRaises(ValueError):validate_snapshot(s,self.out/'public')
 def test_google_places_only_use_independent_curated_coordinates(self):
  with self.store._connection() as c:
   c.execute("insert into trajectory_places(id,name,address,source_url,place_evidence,provider,provider_place_id) values('g','店','東京都','https://google.com','confirmed','google','g-id')")
  s=self.export();self.assertIsNone(s['timeline']['places']['g']['coordinates']);self.assertTrue(s['timeline']['places']['g']['demoPositionUnconfirmed'])
  self.curated.write_text(json.dumps({'g-id':{'name':'店','address':'東京都','coordinates':[139.7,35.6],'sourceUrl':'https://example.org','attribution':'Independent','verifiedAt':'2026-10-05','note':'独立照合'}}))
  s=self.export();self.assertEqual(s['timeline']['places']['g']['coordinates'],[139.7,35.6]);self.assertNotIn('provider',s['timeline']['places']['g'])
