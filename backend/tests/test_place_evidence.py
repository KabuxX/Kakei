import copy,sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from db.store import Store
from db.agent_store import AgentStore
from db.trajectory_store import read_trajectory_timeline
from services.place_evidence import safe_source_url,validate_place_evidence
from services.validation import ValidationError
from web_place_fixtures import SOURCE,PLACE

class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'db';self.store=Store(self.path);self.store.initialize([])
    def test_evidence_round_trip_and_old_schema(self):
        day={'date':'2026-10-03','events':[{'id':'e','time':'09:00','placeId':'p'}],'legs':[]}
        self.store.sync_trajectory({'places':{'p':PLACE},'days':[day]})
        for _ in range(2):
            reopened=Store(self.path)
            saved=reopened.get_trajectory_day(day['date'])['places']['p']
            self.assertEqual(saved['sources'],PLACE['sources']);self.assertEqual(saved['geocoding'],PLACE['geocoding'])
            with reopened._connection() as c:self.assertEqual(read_trajectory_timeline(c)['places']['p'],saved)
        old={k:v for k,v in PLACE.items() if k not in ('sources','geocoding')}
        self.store.sync_trajectory({'places':{'p':old},'days':[day]})
        self.assertEqual(self.store.get_trajectory_day(day['date'])['places']['p'],old)
    def test_message_sources_survive_cached_response(self):
        a=AgentStore(self.path);t=a.create_thread()['id'];a.append_message(t,'old','user','hello')
        lease=a.begin_turn(t,'one','search')
        response=a.complete_turn(t,'one',lease,{'text':'店舗 [source:s1]','sources':[SOURCE],'searchIds':['search1']})
        self.assertEqual(a.begin_turn(t,'one','search')['cached'],response)
        loaded=AgentStore(self.path).get_thread(t)['messages']
        self.assertEqual(loaded[-1]['sources'],response['message']['sources']);self.assertEqual(loaded[-1]['sources'],[SOURCE])
        self.assertEqual(loaded[0]['sources'],[])
    def test_source_urls_preserve_identity(self):
        self.assertEqual(safe_source_url(SOURCE['url']),SOURCE['url'])
        for url in ('javascript:alert(1)','https://user:pass@store.example/','https://localhost/a','https://127.0.0.1/','https://[::1]/','https://10.1.2.3/','https://api.mapbox.com/search?access_token=secret'):
            with self.subTest(url=url),self.assertRaises(ValidationError):safe_source_url(url)
    def test_evidence_rejects_bad_shape_without_truncation(self):
        for patch in ({'sources':[{**SOURCE,'title':'長'*201}]},{'geocoding':{**PLACE['geocoding'],'permanent':False}},{'sources':[{**SOURCE,'retrievedAt':float('nan')}]},{'geocoding':{**PLACE['geocoding'],'key':'secret'}}):
            with self.subTest(patch=patch),self.assertRaises(ValidationError):validate_place_evidence({**PLACE,**patch})
