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
 def test_heic_export_keeps_original_and_provides_browser_preview(self):
  from receipt_image_fixtures import phone_photo
  from test_iphone_receipts import assert_primary_jpeg
  data=phone_photo('HEIF')
  with self.store._connection() as c:
   c.execute('UPDATE receipt_assets SET mime_type=?,data=?,sha256=? WHERE id=?',('image/heic',data,hashlib.sha256(data).hexdigest(),'receipt-1'))
  s=self.export();receipt=s['receipts']['receipt-1']
  self.assertEqual((self.out/'public'/receipt['path']).read_bytes(),data)
  self.assertTrue(receipt['path'].endswith('.heic'))
  preview=self.out/'public'/receipt['previewPath']
  assert_primary_jpeg(self,preview.read_bytes())
  preview.write_bytes(b'corrupt')
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
 def history(self):
  s=self.export();t=s['threads'][0]
  t['receiptReviews']=[{'receiptId':'receipt-1'}]
  t['proposals']=[{'id':'proposal-1','threadId':t['id'],'status':'expired','expiresAt':1,
   'metadata':{'receiptId':'receipt-1','receiptReview':{'receiptId':'receipt-1'}},
   'commands':[{'kind':'transaction.update','identity':{'id':'deleted-transaction'},'data':{'receiptIds':['receipt-1']}}],
   'before':[{'id':'deleted-transaction'}],'after':[{'id':'deleted-transaction','receiptIds':['receipt-1']}],
   'result':{'transactions':[{'id':'deleted-transaction'}]}}]
  return s
 def test_rejects_missing_saved_original_references_with_paths(self):
  for path in ('review','metadata','proposal-review','command','history','result','transaction'):
   with self.subTest(path=path):
    s=self.history();t=s['threads'][0];p=t['proposals'][0]
    if path=='review':t['receiptReviews'][0]['receiptId']='missing-original';expected=r'receiptReviews\[0\].receiptId'
    elif path=='metadata':p['metadata']['receiptId']='missing-original';expected='metadata.receiptId'
    elif path=='proposal-review':p['metadata']['receiptReview']['receiptId']='missing-original';expected='metadata.receiptReview.receiptId'
    elif path=='command':p['commands'][0]['data']['receiptIds']=['missing-original'];expected=r'commands\[0\].data.receiptIds\[0\]'
    elif path=='history':p['after'][0]['receiptIds']=['missing-original'];expected=r'after\[0\].receiptIds\[0\]'
    elif path=='result':p['result']['transactions'][0]['receiptIds']=['missing-original'];expected=r'result.transactions\[0\].receiptIds\[0\]'
    else:s['transactions']=[{'id':'transaction','date':'2026-10-01','receiptIds':['missing-original']}];expected=r'transactions\[0\].receiptIds\[0\]'
    with self.assertRaisesRegex(ValueError,expected):validate_snapshot(s,self.out/'public')
 def test_rejects_parent_mismatches_and_duplicate_lookup_ids(self):
  for case in ('thread','proposal-thread','wrong-proposal-thread','proposal','message','review','receipt-key','receipt-thread'):
   with self.subTest(case=case):
    s=self.history();t=s['threads'][0];p=t['proposals'][0]
    if case=='thread':s['threads'].append(copy.deepcopy(t))
    elif case=='proposal-thread':p['threadId']='missing-thread'
    elif case=='wrong-proposal-thread':s['threads'].append({'id':'another-thread','messages':[],'proposals':[]});p['threadId']='another-thread'
    elif case=='proposal':t['proposals'].append(copy.deepcopy(p))
    elif case=='message':t['messages'].append(copy.deepcopy(t['messages'][0]))
    elif case=='review':t['receiptReviews'].append(copy.deepcopy(t['receiptReviews'][0]))
    elif case=='receipt-key':s['receipts']['receipt-1']['id']='wrong-key'
    else:s['receipts']['receipt-1']['threadId']='missing-thread'
    with self.assertRaises(ValueError):validate_snapshot(s,self.out/'public')
 def test_accepts_pending_expired_and_applied_history_with_deleted_targets(self):
  for status in ('pending','expired','applied'):
   with self.subTest(status=status):
    s=self.history();s['threads'][0]['proposals'][0]['status']=status
    validate_snapshot(s,self.out/'public')
 def test_export_rejects_retained_review_when_original_is_missing(self):
  with self.store._connection() as c:
   c.execute('INSERT INTO agent_turns VALUES (?,?,?,?,?,?,?)',(self.thread['id'],'saved-review','{}','lease','complete',1,json.dumps({'receiptReview':{'receiptId':'missing-original'}})))
  before=self.dump()
  with self.assertRaisesRegex(ValueError,r'receiptReviews\[0\].receiptId'):self.export()
  self.assertEqual(self.dump(),before);self.assertFalse((self.out/'data/snapshot.json').exists())
 def test_rejects_missing_current_transport_reference(self):
  s=self.history();s['timeline']={'places':{'p':{'name':'p','coordinates':[139,35]}},'days':[{'date':'2026-10-01',
   'events':[{'id':'a','placeId':'p'},{'id':'b','placeId':'p'}],
   'legs':[{'fromEventId':'a','toEventId':'b','transportTransactionId':'missing-transaction'}]}]}
  with self.assertRaisesRegex(ValueError,'Missing leg reference'):validate_snapshot(s,self.out/'public')
