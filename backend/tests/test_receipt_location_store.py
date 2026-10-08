"""Receipt confirmation persistence uses isolated databases only."""
import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from db.store import TrajectoryConflict
from db.receipt_location_store import ReceiptLocationStore
from db.merchant_place_store import read_merchant_place, write_merchant_place, clear_merchant_place
from services.receipt_location_contracts import normalize_location_input, location_fingerprint
from services.validation import ValidationError

class ReceiptLocationStoreTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.locations = ReceiptLocationStore(Path(temp.name) / 'test.sqlite3')
        self.input = normalize_location_input({'merchant': '店', 'locality': '東京'})
        with self.locations.store._connection() as c:
            c.execute("INSERT INTO agent_threads VALUES ('t',0,'test')")
            c.execute("INSERT INTO receipt_assets VALUES ('r','t','image/png','hash',1,X'00',0,999999,NULL)")
            c.execute("INSERT INTO transactions (id,title,date,type,category,amount) VALUES ('tx','買物','2026-10-01T12:00','expense','食費',100)")
    def seed(self):
        return self.locations.seed('t','r',self.input,status='needs_input',method=None,now=100)
    def search(self, revision):
        return self.locations.begin_search('t','r',self.input,revision,now=101,processing_until=121)
    def test_limits_and_blank_normalization(self):
        self.assertEqual(normalize_location_input({'merchant':' 店 ','merchantAddress':' \r\n '})['merchantAddress'],None)
        self.assertEqual(normalize_location_input({'merchant':' 店 '})['merchant'],'店')
        for key, limit in [('merchant',200),('branch',200),('locality',200),('merchantAddress',500)]:
            normalize_location_input({'merchant':'店',key:'あ'*limit})
            with self.assertRaises(ValidationError): normalize_location_input({'merchant':'店',key:'あ'*(limit+1)})
        self.assertEqual(location_fingerprint(self.input),location_fingerprint({'locality':'東京','merchant':'店','branch':None,'merchantAddress':None}))
    def test_cas_rejects_old_result(self):
        first=self.search(self.seed()['revision'])
        second=self.search(first['revision'])
        result={'status':'resolved','placeIds':['p'],'selectedPlaceId':'p','method':'google_unique','inputFingerprint':first['inputFingerprint'],'formattedAddress':'SECRET'}
        with self.assertRaises(TrajectoryConflict): self.locations.finish_search('t','r',first['id'],first['revision'],result,now=102)
        done=self.locations.finish_search('t','r',second['id'],second['revision'],result,now=102)
        self.assertEqual(done['selectedPlaceId'],'p')
        with self.locations.store._connection() as c:
            self.assertNotIn('SECRET', str([tuple(r) for r in c.execute('SELECT * FROM receipt_location_resolutions')]))
    def test_recover_search_at_deadline(self):
        location=self.seed(); self.assertEqual(location['expiresAt'],100+86400)
        self.search(location['revision'])
        recovered=self.locations.get('t','r',now=121)
        self.assertEqual(recovered['status'],'unavailable')
        self.assertEqual(self.locations.get('t','r',now=100+86400)['reason'],'expired')
    def test_seed_does_not_overwrite_and_selection_checks_membership(self):
        seeded=self.seed(); self.assertEqual(self.seed(),seeded)
        search=self.search(seeded['revision'])
        selected=self.locations.finish_search('t','r',search['id'],search['revision'],{'status':'needs_selection','placeIds':['p','q']},now=102)
        with self.assertRaises(TrajectoryConflict): self.locations.set_selection('t','r',selected['id'],selected['revision'],'bad',now=103)
        done=self.locations.set_selection('t','r',selected['id'],selected['revision'],'p',now=103)
        self.assertEqual((done['status'],done['method'],done['confirmedAt']),('resolved','google_selected',103))
        with self.assertRaises(TrajectoryConflict): self.locations.set_selection('t','r',selected['id'],selected['revision'],'q',now=104)
    def test_address_and_stale_turn(self):
        seed=self.seed()
        with self.assertRaises(ValidationError): self.locations.set_address('t','r',self.input,seed['revision'],method='user_address',now=101)
        address={**self.input,'merchantAddress':'本人住所'}
        done=self.locations.set_address('t','r',address,seed['revision'],method='user_address',now=101)
        self.assertEqual(done['input']['merchantAddress'],'本人住所')
        search=self.search(done['revision'])
        context={'thread_id':'t','client_message_id':'m','run_token':'old'}
        with self.locations.store._connection() as c: c.execute("INSERT INTO agent_turns VALUES ('t','m','{}','new','processing',101,NULL)")
        with self.assertRaises(TrajectoryConflict): self.locations.finish_search('t','r',search['id'],search['revision'],{'status':'unavailable'},now=102,turn_context=context)
    def test_expired_seed_never_returns_resolved(self):
        address={**self.input,'merchantAddress':'印字住所'}
        self.locations.seed('t','r',address,status='resolved',method='receipt_address',now=100)
        expired=self.locations.seed('t','r',address,status='resolved',method='receipt_address',now=86500)
        self.assertEqual(expired['status'],'unavailable')
        self.assertEqual(expired['reason'],'expired')
        self.assertIsNone(expired['confirmedAt'])
    def test_expired_confirmation_can_be_renewed_but_not_selected(self):
        search=self.search(self.seed()['revision'])
        candidates=self.locations.finish_search('t','r',search['id'],search['revision'],{'status':'needs_selection','placeIds':['p','q']},now=102)
        with self.assertRaises(TrajectoryConflict): self.locations.set_selection('t','r',candidates['id'],candidates['revision'],'p',now=86500)
        expired=self.locations.get('t','r',now=86500)
        renewed=self.locations.begin_search('t','r',self.input,expired['revision'],now=86500,processing_until=86520)
        self.assertEqual(renewed['expiresAt'],86500+86400)
        address=self.locations.set_address('t','r',{**self.input,'merchantAddress':'本人住所'},renewed['revision'],method='user_address',now=172900)
        self.assertEqual((address['status'],address['expiresAt']),('resolved',172900+86400))

    def test_rejects_provider_text_reason_and_excess_candidates(self):
        search=self.search(self.seed()['revision'])
        for result in ({'status':'unavailable','reason':'SECRET provider text'}, {'status':'needs_selection','placeIds':[str(i) for i in range(11)]}):
            with self.assertRaises(ValidationError): self.locations.finish_search('t','r',search['id'],search['revision'],result,now=102)
        self.assertEqual(self.locations.get('t','r',now=102)['status'],'searching')
    def test_receipt_delete_cascades(self):
        self.seed()
        with self.locations.store._connection() as c:
            c.execute("DELETE FROM receipt_assets WHERE id='r'")
            self.assertEqual(c.execute('SELECT COUNT(*) FROM receipt_location_resolutions').fetchone()[0],0)

    def test_delete_cascades_without_changing_transactions(self):
        self.seed()
        with self.locations.store._connection() as c:
            before=tuple(c.execute('SELECT * FROM transactions').fetchone())
            binding={'provider':'google','placeId':'p','method':'google_unique','input':self.input,'confirmedAt':102,'formattedAddress':'SECRET'}
            write_merchant_place(c,'tx',binding)
            self.assertEqual(set(read_merchant_place(c,'tx')),{'provider','placeId','method','input','confirmedAt'})
            clear_merchant_place(c,'tx'); self.assertIsNone(read_merchant_place(c,'tx'))
            write_merchant_place(c,'tx',binding)
            c.execute("DELETE FROM agent_threads WHERE id='t'")
            self.assertEqual(c.execute('SELECT COUNT(*) FROM receipt_location_resolutions').fetchone()[0],0)
            self.assertEqual(tuple(c.execute('SELECT * FROM transactions').fetchone()),before)
            c.execute("DELETE FROM transactions WHERE id='tx'")
            self.assertEqual(c.execute('SELECT COUNT(*) FROM transaction_merchant_places').fetchone()[0],0)
