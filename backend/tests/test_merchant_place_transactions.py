import tempfile
import unittest
from pathlib import Path
from test_merchant_address import DRAFT
from db.store import Store
from db.merchant_place_store import write_merchant_place, read_merchant_place
from services.agent_changes import prepare_changes

class MerchantPlaceTransactionTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        self.store=Store(Path(tmp.name)/'db'); self.store.initialize([])
        self.record=self.store.create_transaction({**DRAFT,'merchantAddress':None})
        self.binding=dict(provider='google',placeId='fixture-one',method='google_selected',input=dict(merchant='店',branch=None,locality=None,merchantAddress=None),confirmedAt=1)
        with self.store._connection() as c: write_merchant_place(c,self.record['id'],self.binding)

    def test_amount_only_full_draft_preserves_null_address_reference(self):
        draft={**DRAFT,'amount':200,'items':[],'merchantAddress':None}
        result=self.store.update_transaction(self.record['id'],draft)
        self.assertEqual(result['merchantPlace']['placeId'],'fixture-one')
        self.assertEqual(self.store.get_transaction(self.record['id'])['merchantPlace'],result['merchantPlace'])
        self.assertEqual(self.store.list_transactions()[0]['merchantPlace'],result['merchantPlace'])

    def test_patch_null_explicitly_clears_reference(self):
        self.store.update_merchant_address(self.record['id'],dict(merchantAddress=None,expected=dict(merchant='店',merchantAddress=None)))
        with self.store._connection() as c: self.assertIsNone(read_merchant_place(c,self.record['id']))

    def test_merchant_address_or_income_change_clears(self):
        for change in [dict(merchant='別店'),dict(merchantAddress='本人住所'),dict(type='income',category='収入')]:
            with self.subTest(change=change):
                with self.store._connection() as c: write_merchant_place(c,self.record['id'],self.binding)
                updated=self.store.update_transaction(self.record['id'],{**DRAFT,**change})
                self.assertNotIn('merchantPlace',updated)
                with self.store._connection() as c: self.assertIsNone(read_merchant_place(c,self.record['id']))
                self.store.update_transaction(self.record['id'],{**DRAFT,'merchantAddress':None})

    def test_agent_preview_preserves_or_removes_reference(self):
        with self.store._connection() as c:
            preview=prepare_changes(c,[dict(kind='transaction.update',identity=dict(id=self.record['id']),data={**DRAFT,'merchantAddress':None})])
            self.assertEqual(preview['before'][0]['merchantPlace']['placeId'],'fixture-one')
            self.assertEqual(preview['after'][0]['merchantPlace']['placeId'],'fixture-one')
            preview=prepare_changes(c,[dict(kind='transaction.update',identity=dict(id=self.record['id']),data={**DRAFT,'merchant':'別店'})])
            self.assertNotIn('merchantPlace',preview['after'][0])

    def test_delete_cascades(self):
        self.store.delete_transaction(self.record['id'])
        with self.store._connection() as c: self.assertIsNone(read_merchant_place(c,self.record['id']))

    def test_agent_apply_uses_same_clear_policy(self):
        from db.agent_store import AgentStore
        from agent.contracts import AgentCommand
        agent=AgentStore(self.store.db_path)
        thread=agent.create_thread()['id']
        for change,preserves in [({'amount':200,'items':[],'merchantAddress':None},True),({'merchant':'別店'},False)]:
            proposal=agent.create_proposal(thread,[AgentCommand('transaction.update',{'id':self.record['id']},{**DRAFT,**change})],{})
            result=self.store.apply_agent_proposal(proposal['id'],1)['transactions'][0]
            saved=self.store.get_transaction(self.record['id'])
            self.assertEqual('merchantPlace' in result,preserves)
            self.assertEqual('merchantPlace' in saved,preserves)

    def test_normalized_comparison_preserves_reference(self):
        from db.merchant_place_store import should_clear_merchant_place
        self.assertFalse(should_clear_merchant_place(self.record,{**DRAFT,'merchant':' 店 ','merchantAddress':''}))
        self.assertTrue(should_clear_merchant_place(self.record,{'merchantAddress':None},address_only=True))
