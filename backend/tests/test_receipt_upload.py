import io, json, sys, tempfile, unittest, time
from datetime import datetime, timezone, timedelta
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PIL import Image
from pypdf import PdfWriter
from fastapi.testclient import TestClient
from api.app import create_app
from db.agent_store import AgentStore
from db.receipt_store import ReceiptStore
from services.receipt_validation import validate_receipt
from services.validation import ValidationError

def png():
    stream=io.BytesIO();Image.new('RGB',(4,4),'white').save(stream,format='PNG');return stream.getvalue()
def pdf(pages=1,encrypted=False):
    writer=PdfWriter()
    for _ in range(pages): writer.add_blank_page(width=100,height=100)
    if encrypted: writer.encrypt('password')
    stream=io.BytesIO();writer.write(stream);return stream.getvalue()

class ReceiptUploadTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        root=Path(self.temp.name);self.path=root/'db';self.app=create_app(self.path,root);self.app.state.store.initialize([])
        self.agent=AgentStore(self.path);self.thread=self.agent.create_thread()['id'];self.receipts=ReceiptStore(self.path)
        self.client=TestClient(self.app,base_url='http://localhost:8765',headers={'Origin':'http://localhost:8765'});self.addCleanup(self.client.close)
    def upload(self,data=None,name='receipt.png'):
        return self.client.post(f'/api/agent/threads/{self.thread}/receipts',files={'file':(name,png() if data is None else data)})
    def test_upload_png_and_pdf(self):
        for data,name,mime in [(png(),'a.png','image/png'),(pdf(),'a.pdf','application/pdf')]:
            response=self.upload(data,name);self.assertEqual(response.status_code,201,response.text)
            identifier=response.json()['id'];preview=self.client.get(f'/api/agent/threads/{self.thread}/receipts/{identifier}')
            self.assertEqual(preview.content,data);self.assertEqual(preview.headers['content-type'],mime)
            self.assertEqual(self.client.get('/api/receipts/'+identifier).status_code,404)
            self.assertEqual(self.client.get(f'/api/agent/threads/wrong/receipts/{identifier}').status_code,404)
    def test_reject_spoofed_corrupt_encrypted_and_four_page_files(self):
        for data,name in [(png(),'a.pdf'),(png()+b'<script>evil</script>','a.png'),(b'corrupt','a.jpg'),(pdf(4),'a.pdf'),(pdf(encrypted=True),'a.pdf')]:
            with self.subTest(name=name): self.assertEqual(self.upload(data,name).status_code,400)
    def test_10_mib_limit_does_not_store_asset(self):
        self.assertEqual(self.upload(b'x'*(10*1024*1024+1)).status_code,413)
        with self.app.state.store._connection() as c:self.assertEqual(c.execute('SELECT count(*) FROM receipt_assets').fetchone()[0],0)
    def test_duplicate_hash_reports_existing_receipt(self):
        first=self.upload().json();second=self.upload().json();self.assertEqual(first['id'],second['id'])
        self.assertIn(first['id'],second['duplicateReceiptIds'])
    def test_pending_expiry_and_thread_delete(self):
        identifier=self.upload().json()['id']
        self.assertEqual(self.receipts.expire_pending(datetime.now(timezone.utc)+timedelta(days=2)),1)
        self.assertIsNone(self.receipts.get_asset(identifier))
        identifier=self.upload().json()['id'];self.agent.delete_thread(self.thread)
        self.assertIsNone(self.receipts.get_asset(identifier))

    def receipt_proposal(self, receipt_id, thread=None, target=None):
        draft={'title':'食材','date':'2026-10-03T12:00','type':'expense','category':'食費','merchant':'店','amount':100,'paymentMethod':'cash','receiptIds':[receipt_id]}
        # Simulate an already-issued legacy row; new generic attachment is forbidden.
        command={'kind':'transaction.update' if target else 'transaction.create','identity':{'id':target} if target else {},'data':draft}
        with self.app.state.store._connection() as c:
            ReceiptStore.validate_commands(c, [command], thread or self.thread)
        proposal=self.agent.create_proposal(thread or self.thread,[{**command,'data':{k:v for k,v in draft.items() if k!='receiptIds'}}])
        with self.app.state.store._connection() as c:
            c.execute('UPDATE agent_proposals SET commands_json=? WHERE id=?',(json.dumps([command]),proposal['id']))
        return self.agent.get_proposal(proposal['id'])
    def test_approval_attaches_receipt_once_and_delete_cleans_asset(self):
        identifier=self.upload().json()['id'];proposal=self.receipt_proposal(identifier)
        first=self.app.state.store.apply_agent_proposal(proposal['id'],1)
        self.assertEqual(first,self.app.state.store.apply_agent_proposal(proposal['id'],1))
        tx=first['transactions'][0]['id']
        self.assertEqual(self.receipts.list_for_transaction(tx)[0]['id'],identifier)
        self.assertEqual(self.client.get('/api/receipts/'+identifier).content,png())
        self.assertEqual(self.client.get('/api/transactions/'+tx+'/receipts').json()['receipts'][0]['id'],identifier)
        self.app.state.store.delete_transaction(tx);self.assertIsNone(self.receipts.get_asset(identifier))
    def test_reject_discards_pending_and_wrong_thread_fails(self):
        identifier=self.upload().json()['id'];other=self.agent.create_thread()['id']
        with self.assertRaises((ValidationError,ValueError)):
            self.receipt_proposal(identifier,thread=other)
        proposal=self.receipt_proposal(identifier);self.agent.reject_proposal(proposal['id'],1)
        self.assertIsNone(self.receipts.get_asset(identifier))
    def test_rollback_keeps_pending_receipt(self):
        from unittest.mock import patch
        identifier=self.upload().json()['id'];proposal=self.receipt_proposal(identifier)
        with patch.object(ReceiptStore,'attach',side_effect=ValidationError('receipt','forced')),self.assertRaises(ValidationError):
            self.app.state.store.apply_agent_proposal(proposal['id'],1)
        self.assertEqual(self.app.state.store.list_transactions(),[])
        self.assertIsNone(self.receipts.get_asset(identifier)['transaction_id'])
    def test_edit_attaches_to_selected_existing_transaction(self):
        tx=self.app.state.store.create_transaction({'title':'給与','date':'2026-10-03T12:00','type':'income','category':'収入','amount':100})
        identifier=self.upload().json()['id'];proposal=self.receipt_proposal(identifier,target=tx['id'])
        self.app.state.store.apply_agent_proposal(proposal['id'],1)
        self.assertEqual(self.receipts.list_for_transaction(tx['id'])[0]['id'],identifier)
        self.assertEqual(len(self.app.state.store.list_transactions()),1)

    def test_review_requires_explicit_target_and_is_idempotent(self):
        identifier=self.upload().json()['id']
        lease=self.agent.begin_turn(self.thread,'receipt','読取',identifier)
        self.agent.complete_turn(self.thread,'receipt',lease,{'text':'確認','commands':[],'receiptReview':{'receiptId':identifier,'matches':[]}})
        draft={'title':'食材','date':'2026-10-03T12:00','type':'expense','category':'食費','merchant':'店','amount':100,'paymentMethod':'cash'}
        url=f'/api/agent/threads/{self.thread}/receipt-proposals'
        body={'receiptId':identifier,'target':'','draft':draft,'currency':'JPY'}
        self.assertEqual(self.client.post(url,json=body).status_code,400)
        body['target']='new'
        self.assertEqual(self.client.post(url,json=body).status_code,400)
        from db.receipt_location_store import ReceiptLocationStore
        draft['merchantAddress']='本人住所'
        r=ReceiptLocationStore(self.path).seed(self.thread,identifier,{'merchant':'店','merchantAddress':'本人住所'},status='resolved',method='receipt_address',now=time.time())
        body['location']={'resolutionId':r['id'],'revision':r['revision'],'input':r['input']}
        first=self.client.post(url,json=body)
        self.assertEqual(first.status_code,201,first.text)
        self.assertEqual(first.json()['proposal']['id'],self.client.post(url,json=body).json()['proposal']['id'])

    def test_receipt_address_persists_with_original_and_omission_preserves_it(self):
        from agent.receipt import ReceiptCandidate,receipt_review
        from test_merchant_address import DRAFT
        identifier=self.upload().json()['id']
        review=receipt_review(ReceiptCandidate(merchant='店',merchant_address='住所A'),[],identifier)
        lease=self.agent.begin_turn(self.thread,'address-receipt','読取',identifier)
        self.agent.complete_turn(self.thread,'address-receipt',lease,{'text':'確認','commands':[],'receiptReview':review})
        from db.receipt_location_store import ReceiptLocationStore
        r=ReceiptLocationStore(self.path).seed(self.thread,identifier,{'merchant':'店','merchantAddress':'住所A'},status='resolved',method='receipt_address',now=time.time())
        proposal=self.agent.create_receipt_proposal(self.thread,identifier,'new',{**DRAFT,'merchantAddress':review['candidate']['merchant_address']},'JPY',location={'resolutionId':r['id'],'revision':r['revision'],'input':r['input']})
        result=self.app.state.store.apply_agent_proposal(proposal['id'],1)
        tx=result['transactions'][0]
        self.assertEqual(self.app.state.store.get_transaction(tx['id'])['merchantAddress'],'住所A')
        self.assertEqual(self.receipts.list_for_transaction(tx['id'])[0]['id'],identifier)
        self.assertEqual(self.agent.get_proposal(proposal['id'])['metadata']['receiptReview']['candidate']['merchant_address'],'住所A')
        # Ordinary receipt-compatible update without address cannot erase it.
        self.app.state.store.update_transaction(tx['id'],DRAFT)
        self.assertEqual(self.app.state.store.get_transaction(tx['id'])['merchantAddress'],'住所A')
