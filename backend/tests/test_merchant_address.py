import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from db.store import Store, TrajectoryConflict
from db.agent_store import AgentStore
from agent.contracts import AgentCommand
from services.validation import ValidationError, normalize_transaction

DRAFT = dict(title='昼食', date='2026-10-01T12:00', type='expense', category='食費', amount=100, merchant='店', paymentMethod='cash', items=[dict(name='パン',amount=100)])

class MerchantAddressTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        self.path = Path(tmp.name)/'db.sqlite3'
        self.store = Store(self.path); self.store.initialize([])
        self.agent = AgentStore(self.path); self.thread = self.agent.create_thread()['id']

    def test_address_value_limits(self):
        for value, expected in [(' \r\n東京都千代田区\r\n二番町8-8 ', '東京都千代田区\n二番町8-8'), ('𠮷'*500,'𠮷'*500), ('   ',None), (None,None)]:
            self.assertEqual(normalize_transaction({**DRAFT,'merchantAddress':value}).get('merchantAddress'),expected)
        for value in ['𠮷'*501, 1, [], {}]:
            for imported in [False,True]:
                with self.subTest(value=str(value)[:20],imported=imported), self.assertRaises(ValidationError):
                    normalize_transaction({**DRAFT, **({'id':'import'} if imported else {}),'merchantAddress':value},import_mode=imported)

    def test_omitted_address_survives_put_and_agent_update(self):
        record=self.store.create_transaction({**DRAFT,'merchantAddress':'住所A'})
        updated=self.store.update_transaction(record['id'],DRAFT)
        self.assertEqual(updated.get('merchantAddress'),'住所A')
        p=self.agent.create_proposal(self.thread,[AgentCommand('transaction.update',{'id':record['id']},DRAFT)],{})
        self.store.apply_agent_proposal(p['id'],1)
        saved=Store(self.path).get_transaction(record['id'])
        self.assertEqual(saved.get('merchantAddress'),'住所A'); self.assertEqual(saved['items'],DRAFT['items']); self.assertFalse(saved['timeEstimated'])
        with self.assertRaises(ValidationError): self.store.update_transaction(record['id'],{**DRAFT,'merchant':'別店舗'})
        for value in [None,'']:
            self.store.update_transaction(record['id'],{**DRAFT,'merchantAddress':value})
            self.assertIsNone(self.store.get_transaction(record['id'])['merchantAddress'])
        self.store.update_transaction(record['id'],{**DRAFT,'merchantAddress':'住所A'})
        self.store.update_transaction(record['id'],{**DRAFT,'type':'income','category':'収入'})
        self.assertNotIn('merchantAddress',self.store.get_transaction(record['id']))
        with self.store._connection() as c: self.assertIsNone(c.execute('SELECT merchant_address FROM transactions').fetchone()[0])

    def test_legacy_proposal_address_baseline(self):
        record=self.store.create_transaction(DRAFT)
        for changed in [False,True]:
            p=self.agent.create_proposal(self.thread,[AgentCommand('transaction.update',{'id':record['id']},DRAFT)],{})
            old={k:v for k,v in record.items() if k!='merchantAddress'}
            digest=hashlib.sha256(json.dumps(old,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
            with self.store._connection() as c: c.execute('UPDATE agent_proposals SET baselines_json=? WHERE id=?',(json.dumps({'transaction:'+record['id']:digest}),p['id']))
            if changed:
                self.store.update_transaction(record['id'],{**DRAFT,'merchantAddress':'住所B'})
                with self.assertRaises(TrajectoryConflict): self.store.apply_agent_proposal(p['id'],1)
            else: self.store.apply_agent_proposal(p['id'],1)

    def test_address_migration_preserves_records(self):
        record=self.store.create_transaction({**DRAFT,'merchantAddress':'住所A'})
        for _ in range(2): self.assertEqual(Store(self.path).get_transaction(record['id']).get('merchantAddress'),'住所A')
        with self.store._connection() as c:
            self.assertEqual(c.execute('SELECT merchant_address FROM agent_transactions').fetchone()[0],'住所A')
