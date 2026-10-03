from test_receipt_upload import ReceiptUploadTests
from agent.receipt import ReceiptCandidate
from services.receipt_matching import find_receipt_matches
class MatchingTests(ReceiptUploadTests):
    def test_hash_and_near_match_candidates(self):
        tx=self.app.state.store.create_transaction({'title':'食材','date':'2026-10-03T12:00','type':'expense','category':'食費','merchant':'ＡＢＣ Shop','amount':100,'paymentMethod':'cash'})
        with self.app.state.store._connection() as c:
            matches=find_receipt_matches(c,ReceiptCandidate(merchant='abc shop',date='2026-10-01',total=100),'x')
        self.assertEqual(matches[0]['transaction']['id'],tx['id']);self.assertEqual(matches[0]['reason'],'near')
        with self.app.state.store._connection() as c:
            self.assertEqual(find_receipt_matches(c,ReceiptCandidate(merchant='abc shop',date='2026-09-01',total=100),'x'),[])
