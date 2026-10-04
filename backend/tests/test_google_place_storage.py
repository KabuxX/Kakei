import copy, sqlite3, sys, tempfile, time, unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from db.store import Store
from db.google_place_cache import write_cached_coordinates, read_cached_coordinates, purge_expired_coordinates
from services.google_place_display import GooglePlaceDisplay
from services.agent_places import source_version
from agent.google_places import GoogleCandidate, GooglePlacesError
from services.trajectory_mutation import parse_trajectory_command
from google_places_fixtures import place

GOOGLE={'name':'記録の店舗','address':None,'sourceUrl':None,'placeEvidence':'google_places','provider':'google','providerPlaceId':'fixture-chiyoda'}
LEGACY={'name':'旧地点','address':'東京都千代田区','coordinates':[139.7,35.6],'sourceUrl':'https://example.com/old'}

def timeline():
    return {'places':{'g':copy.deepcopy(GOOGLE),'old':copy.deepcopy(LEGACY)},'days':[
        {'date':'2027-03-01','events':[{'id':'e','placeId':'g','time':'12:00','timeEvidence':'exact'}],'legs':[]}]}

class Client:
    def __init__(self,fail=False):self.fail=fail
    async def details(self,identifier):
        if self.fail:raise GooglePlacesError('unavailable')
        return GoogleCandidate.from_payload(place())

class GoogleStorageTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'db'
        self.store=Store(self.path); self.store.initialize([])

    async def test_legacy_migration_and_google_without_coordinates(self):
        legacy_path=Path(self.temp.name)/'legacy'
        with sqlite3.connect(legacy_path) as connection:
            connection.executescript((Path(__file__).parent/'fixtures/trajectory_legacy.sql').read_text())
            connection.execute("INSERT INTO trajectory_places VALUES ('old','旧地点','東京都千代田区',139.7,35.6,'https://example.com/old')")
            connection.execute("INSERT INTO trajectory_days VALUES ('2027-03-02')")
            connection.execute("INSERT INTO trajectory_events VALUES ('old-e','2027-03-02',0,'12:00','old',NULL)")
        legacy=Store(legacy_path)
        self.assertEqual(legacy.get_trajectory_day('2027-03-02')['places']['old']['coordinates'],[139.7,35.6])
        self.store.sync_trajectory(timeline())
        reopened=Store(self.path).get_trajectory_day('2027-03-01')
        self.assertEqual(reopened['places']['g']['providerPlaceId'],'fixture-chiyoda')
        self.assertNotIn('coordinates',reopened['places']['g'])
        with self.store._connection() as connection:
            self.assertEqual(connection.execute('PRAGMA foreign_key_check').fetchall(),[])

    async def test_expiry_and_failed_rehydration_keep_visit(self):
        self.store.sync_trajectory(timeline());now=time.time()
        with self.store._connection() as connection:
            write_cached_coordinates(connection,'fixture-chiyoda',(139,35),now-30*86400)
            self.assertIsNone(read_cached_coordinates(connection,'fixture-chiyoda',now))
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM google_place_coordinates').fetchone()[0],0)
        missing=await GooglePlaceDisplay(self.store,Client(True)).hydrate(self.store.get_trajectory_day('2027-03-01'),now=now)
        self.assertEqual(len(missing['days'][0]['events']),1)
        self.assertIsNone(missing['places']['g']['coordinates'])
        self.assertEqual(missing['places']['g']['locationResolution'],'unavailable')
        hydrated=await GooglePlaceDisplay(self.store,Client()).hydrate(missing,now=now)
        self.assertEqual(hydrated['places']['g']['coordinates'],[139.737,35.685])
        self.assertNotIn('coordinates',self.store.get_trajectory_day('2027-03-01')['places']['g'])

    async def test_cache_does_not_change_source_version(self):
        self.store.sync_trajectory(timeline());now=time.time()
        with self.store._connection() as connection:
            before=source_version(connection)
            write_cached_coordinates(connection,'fixture-chiyoda',(139,35),now)
            self.assertEqual(source_version(connection),before)
            self.assertEqual(purge_expired_coordinates(connection,now+30*86400),1)
            self.assertEqual(source_version(connection),before)

    async def test_other_day_edit_and_old_proposal_keep_google_reference(self):
        self.store.sync_trajectory(timeline())
        self.store.mutate_trajectory(parse_trajectory_command({'kind':'day','date':'2027-03-02','data':{'events':[],'legs':[]}},'POST'),'create')
        self.assertEqual(self.store.get_trajectory_day('2027-03-01')['places']['g'],GOOGLE)
        from db.agent_store import AgentStore
        repo=AgentStore(self.path);thread=repo.create_thread()['id']
        proposal=repo.create_proposal(thread,[{'kind':'trajectory.update','identity':{'kind':'day','date':'2027-03-02'},'data':{'events':[],'legs':[]}}])
        self.store.apply_agent_proposal(proposal['id'],proposal['revision'])
        self.assertEqual(self.store.get_trajectory_day('2027-03-01')['places']['g'],GOOGLE)

    async def test_google_reference_rejects_durable_coordinates(self):
        bad=timeline();bad['places']['g']['coordinates']=[139,35]
        with self.assertRaises(ValueError):self.store.sync_trajectory(bad)

    async def test_attributions_are_hydrated_on_cache_hit_without_persisting(self):
        self.store.sync_trajectory(timeline());now=time.time()
        attribution={'provider':'合成資料提供者','providerUri':'https://example.com/provider'}
        class AttributedClient:
            calls=0
            async def details(self,identifier):
                self.calls+=1;payload=place();payload['attributions']=[attribution]
                return GoogleCandidate.from_payload(payload)
        with self.store._connection() as connection:write_cached_coordinates(connection,'fixture-chiyoda',(139,35),now)
        client=AttributedClient();hydrated=await GooglePlaceDisplay(self.store,client).hydrate(self.store.get_trajectory_day('2027-03-01'),now=now)
        self.assertEqual(hydrated['places']['g']['attributions'],[attribution]);self.assertEqual(client.calls,1)
        self.assertNotIn('attributions',self.store.get_trajectory_day('2027-03-01')['places']['g'])
        missing=await GooglePlaceDisplay(self.store,Client(True)).hydrate(self.store.get_trajectory_day('2027-03-01'),now=now)
        self.assertIsNone(missing['places']['g']['coordinates']);self.assertEqual(len(missing['days'][0]['events']),1)
