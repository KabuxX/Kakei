import copy, json, sys, tempfile, time, unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from db.agent_store import AgentStore
from db.receipt_store import ReceiptStore
from db.receipt_location_store import ReceiptLocationStore
from db.merchant_place_store import write_merchant_place, read_merchant_place
from db.store import TrajectoryConflict
from services.validation import ValidationError
from test_receipt_upload import png
from services.receipt_validation import validate_receipt

DRAFT={'title':'食材','date':'2026-10-03T12:00','type':'expense','category':'食費','merchant':'店','merchantAddress':None,'amount':100,'paymentMethod':'cash'}

class ProposalTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
        self.agent=AgentStore(Path(tmp.name)/'db');self.store=self.agent.store;self.store.initialize([])
        self.thread=self.agent.create_thread()['id'];self.assets=ReceiptStore(self.store.db_path)
        self.receipt=self.assets.create_pending(self.thread,validate_receipt(png(),'a.png'))['id']
        self.locations=ReceiptLocationStore(self.store.db_path)
        self.target='new'
        self.review={'receiptId':self.receipt,'matches':[]}
    def review_turn(self):
        lease=self.agent.begin_turn(self.thread,'read','読取',self.receipt)
        self.agent.complete_turn(self.thread,'read',lease,{'text':'確認','receiptReview':self.review})
    def resolve(self,address=None):
        now=time.time();current=self.locations.get(self.thread,self.receipt,now=now)
        if current is None:current=self.locations.seed(self.thread,self.receipt,{'merchant':'店'},status='needs_input',method=None,now=now)
        if address:
            r=self.locations.set_address(self.thread,self.receipt,{'merchant':'店','merchantAddress':address},current['revision'],method='user_address',now=now)
        else:
            r=self.locations.begin_search(self.thread,self.receipt,{'merchant':'店'},current['revision'],now=now,processing_until=now+20)
            r=self.locations.finish_search(self.thread,self.receipt,r['id'],r['revision'],{'status':'resolved','method':'google_unique','placeIds':['p'],'selectedPlaceId':'p'},now=now)
        return {'resolutionId':r['id'],'revision':r['revision'],'input':r['input']}
    def proposal(self,location=None,draft=None):
        return self.agent.create_receipt_proposal(self.thread,self.receipt,self.target,draft or DRAFT,'JPY',location=location)
    def test_unresolved_create_rejected(self):
        self.review_turn()
        with self.assertRaises(ValidationError):self.proposal()
    def test_resolved_reference_saved_atomically(self):
        self.review_turn();p=self.proposal(self.resolve());first=self.store.apply_agent_proposal(p['id'],1)
        self.assertEqual(first,self.store.apply_agent_proposal(p['id'],1));tx=first['transactions'][0]
        self.assertIsNone(tx['merchantAddress'])
        with self.store._connection() as c:self.assertEqual(read_merchant_place(c,tx['id'])['placeId'],'p')
        self.assertEqual(self.assets.get_asset(self.receipt)['transaction_id'],tx['id'])
    def test_place_only_conflict_blocks_approval(self):
        tx=self.store.create_transaction(DRAFT);self.target=tx['id'];self.review['matches']=[{'transaction':tx}];self.review_turn()
        p=self.proposal(self.resolve())
        with self.store._connection() as c:write_merchant_place(c,tx['id'],{'provider':'google','placeId':'changed','method':'google_selected','input':{'merchant':'店'},'confirmedAt':time.time()})
        with self.assertRaises(TrajectoryConflict):self.store.apply_agent_proposal(p['id'],1)
    def test_reconfirmation_updates_same_pending_proposal(self):
        self.review_turn();p=self.proposal(self.resolve());loc=self.resolve('本人住所')
        r=self.agent.revise_receipt_proposal_location(p['id'],1,{**DRAFT,'merchantAddress':'本人住所'},loc)
        self.assertEqual(r['id'],p['id']);self.assertEqual(r['revision'],2)
        tx=self.store.apply_agent_proposal(r['id'],2)['transactions'][0];self.assertEqual(tx['merchantAddress'],'本人住所')
    def test_amount_edit_keeps_binding_but_merchant_edit_rejected(self):
        self.review_turn();p=self.proposal(self.resolve());commands=copy.deepcopy(p['commands']);commands[0]['data']['amount']=200
        r=self.agent.revise_proposal(p['id'],1,commands);self.assertEqual(r['metadata']['receiptLocation'],p['metadata']['receiptLocation'])
        commands[0]['data']['merchant']='別店舗'
        with self.assertRaises(ValidationError):self.agent.revise_proposal(p['id'],2,commands)
    def test_old_proposal_remains_approvable(self):
        p=self.agent.create_proposal(self.thread,[{'kind':'transaction.create','identity':{},'data':DRAFT}])
        self.assertEqual(len(self.store.apply_agent_proposal(p['id'],1)['transactions']),1)
    def test_location_write_failure_rolls_back_everything(self):
        self.review_turn();p=self.proposal(self.resolve())
        with patch('services.receipt_location_proposals.apply_receipt_location',side_effect=ValidationError('location','forced')),self.assertRaises(ValidationError):self.store.apply_agent_proposal(p['id'],1)
        self.assertEqual(self.store.list_transactions(),[]);self.assertIsNone(self.assets.get_asset(self.receipt)['transaction_id']);self.assertEqual(self.agent.get_proposal(p['id'])['status'],'pending')
    def test_confirmation_is_fixed_when_form_researched(self):
        self.review_turn();p=self.proposal(self.resolve());self.resolve('新住所')
        self.store.apply_agent_proposal(p['id'],1)
    def test_input_reference_tampering_rejected(self):
        self.review_turn();loc=self.resolve();loc['input']['locality']='別地域'
        with self.assertRaises(ValidationError):self.proposal(loc)
    def test_google_update_explicitly_erases_old_address(self):
        tx=self.store.create_transaction({**DRAFT,'merchantAddress':'旧住所'});self.target=tx['id'];self.review['matches']=[{'transaction':tx}];self.review_turn()
        p=self.proposal(self.resolve());self.assertEqual(p['before'][0]['merchantAddress'],'旧住所');self.assertIsNone(p['after'][0]['merchantAddress'])
    def test_reference_addition_is_visible_in_preview(self):
        self.review_turn();p=self.proposal(self.resolve())
        self.assertEqual(p['after'][0]['merchantPlace'],{'provider':'google','placeId':'p','method':'google_unique'})
    def test_expired_binding_cannot_be_approved(self):
        self.review_turn();p=self.proposal(self.resolve())
        with self.store._connection() as c:
            metadata=p['metadata'];metadata['receiptLocation']['expiresAt']=time.time()-1
            c.execute('UPDATE agent_proposals SET metadata_json=? WHERE id=?',(json.dumps(metadata),p['id']))
        with self.assertRaises(ValidationError):self.store.apply_agent_proposal(p['id'],1)
    def test_reopened_thread_uses_latest_confirmation(self):
        self.review_turn();loc=self.resolve('本人住所')
        review=self.agent.get_thread(self.thread)['receiptReviews'][0]
        self.assertEqual(review['locationResolution']['revision'],loc['revision'])
        with self.store._connection() as c:c.execute('UPDATE receipt_location_resolutions SET expires_at=?',(time.time()-1,))
        self.assertEqual(self.agent.get_thread(self.thread)['receiptReviews'][0]['locationResolution']['reason'],'expired')
    def test_existing_transaction_confirmation_cannot_change_target(self):
        tx=self.store.create_transaction({**DRAFT,'merchantAddress':'本人住所'})
        now=time.time();r=self.locations.seed(self.thread,self.receipt,{'merchant':'店'},status='needs_input',method=None,now=now)
        r=self.locations.set_address(self.thread,self.receipt,{'merchant':'店','merchantAddress':'本人住所'},r['revision'],method='existing_address',source_transaction_id=tx['id'],now=now)
        self.review_turn()
        with self.assertRaises(ValidationError):self.proposal({'resolutionId':r['id'],'revision':r['revision'],'input':r['input']},{**DRAFT,'merchantAddress':'本人住所'})
    def test_legacy_revision_preserves_legacy_baseline_keys(self):
        tx=self.store.create_transaction(DRAFT);command={'kind':'transaction.update','identity':{'id':tx['id']},'data':DRAFT}
        p=self.agent.create_proposal(self.thread,[command])
        with self.store._connection() as c:
            row=c.execute('SELECT baselines_json FROM agent_proposals WHERE id=?',(p['id'],)).fetchone();keys=json.loads(row[0]);keys.pop('merchant-place:'+tx['id'],None)
            c.execute('UPDATE agent_proposals SET baselines_json=? WHERE id=?',(json.dumps(keys),p['id']))
        self.agent.revise_proposal(p['id'],1,[command])
        with self.store._connection() as c:self.assertNotIn('merchant-place:'+tx['id'],json.loads(c.execute('SELECT baselines_json FROM agent_proposals WHERE id=?',(p['id'],)).fetchone()[0]))
    def test_revision_cannot_remove_original_attachment(self):
        self.review_turn();p=self.proposal(self.resolve());commands=copy.deepcopy(p['commands']);commands[0]['data'].pop('receiptIds')
        with self.assertRaises(ValidationError):self.agent.revise_proposal(p['id'],1,commands)
    def test_reconfirmation_route_and_stale_revision(self):
        from fastapi.testclient import TestClient
        from api.app import create_app
        self.review_turn();p=self.proposal(self.resolve());loc=self.resolve('本人住所')
        app=create_app(self.store.db_path,Path(self.store.db_path).parent)
        with TestClient(app,base_url='http://localhost:8765',headers={'origin':'http://localhost:8765'}) as client:
            url='/api/agent/proposals/'+p['id']+'/receipt-location'
            body={'revision':1,'draft':{**DRAFT,'merchantAddress':'本人住所'},'location':loc}
            response=client.post(url,json=body);self.assertEqual(response.status_code,200,response.text)
            self.assertEqual(response.json()['proposal']['id'],p['id']);self.assertEqual(response.json()['proposal']['revision'],2)
            self.assertEqual(client.post(url,json=body).status_code,409)
    def test_expired_receipt_does_not_restore_old_resolved_review(self):
        loc=self.resolve('本人住所');r=self.locations.get(self.thread,self.receipt,now=time.time())
        self.review['locationResolution']=r;self.review_turn()
        with self.store._connection() as c:c.execute('UPDATE receipt_assets SET expires_at=? WHERE id=?',(time.time()-1,self.receipt))
        self.assertEqual(self.agent.get_thread(self.thread)['receiptReviews'][0]['locationResolution']['status'],'unavailable')
    def test_google_search_with_user_address_keeps_evidence_but_erases_address_column(self):
        self.review_turn();now=time.time();value={'merchant':'店','merchantAddress':'本人検索条件住所'}
        r=self.locations.seed(self.thread,self.receipt,value,status='needs_input',method=None,now=now)
        r=self.locations.begin_search(self.thread,self.receipt,value,r['revision'],now=now,processing_until=now+20)
        r=self.locations.finish_search(self.thread,self.receipt,r['id'],r['revision'],{'status':'resolved','method':'google_unique','placeIds':['p'],'selectedPlaceId':'p'},now=now)
        p=self.proposal({'resolutionId':r['id'],'revision':r['revision'],'input':r['input']},{**DRAFT,'merchantAddress':'本人検索条件住所'})
        self.assertIsNone(p['commands'][0]['data']['merchantAddress']);self.assertEqual(p['metadata']['receiptLocation']['input']['merchantAddress'],'本人検索条件住所')
        self.assertIsNone(self.store.apply_agent_proposal(p['id'],1)['transactions'][0]['merchantAddress'])
    def test_google_revision_cannot_omit_explicit_address_erasure(self):
        tx=self.store.create_transaction({**DRAFT,'merchantAddress':'旧住所'});self.target=tx['id'];self.review['matches']=[{'transaction':tx}];self.review_turn()
        p=self.proposal(self.resolve());commands=copy.deepcopy(p['commands']);commands[0]['data'].pop('merchantAddress')
        with self.assertRaises(ValidationError):self.agent.revise_proposal(p['id'],1,commands)
    def test_present_but_empty_binding_is_not_legacy(self):
        self.review_turn();p=self.proposal(self.resolve());metadata=p['metadata']
        for invalid in (None,{}):
            with self.subTest(invalid=invalid):
                metadata['receiptLocation']=invalid
                with self.store._connection() as c:c.execute('UPDATE agent_proposals SET metadata_json=? WHERE id=?',(json.dumps(metadata),p['id']))
                with self.assertRaises(ValidationError):self.store.apply_agent_proposal(p['id'],1)
    def test_reconfirmation_store_requires_integer_revision(self):
        self.review_turn();p=self.proposal(self.resolve());loc=self.resolve('本人住所')
        for revision in (None,True,False,'1',1.0):
            with self.subTest(revision=revision):
                with self.assertRaises(ValidationError):
                    self.agent.revise_receipt_proposal_location(p['id'],revision,{**DRAFT,'merchantAddress':'本人住所'},loc)
                self.assertEqual(self.agent.get_proposal(p['id']),p)
    def test_reconfirmation_api_requires_explicit_integer_revision(self):
        from fastapi.testclient import TestClient
        from api.app import create_app
        self.review_turn();p=self.proposal(self.resolve());loc=self.resolve('本人住所')
        app=create_app(self.store.db_path,Path(self.store.db_path).parent)
        with TestClient(app,base_url='http://localhost:8765',headers={'origin':'http://localhost:8765'}) as client:
            url='/api/agent/proposals/'+p['id']+'/receipt-location'
            body={'draft':{**DRAFT,'merchantAddress':'本人住所'},'location':loc}
            for value in ({}, {'revision':None}, {'revision':True}, {'revision':False}, {'revision':'1'}, {'revision':1.0}):
                with self.subTest(value=value):
                    response=client.post(url,json={**body,**value})
                    self.assertEqual(response.status_code,400,response.text)
                    self.assertEqual(response.json()['error']['field'],'revision')
                    self.assertEqual(self.agent.get_proposal(p['id']),p)
