import copy,sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from db.store import Store
from services.trajectory_validation import validate_timeline
from services.trajectory_mutation import parse_trajectory_command
from services.validation import ValidationError
PLACE={'name':'海外の地点','address':None,'coordinates':[-73.9,40.7],'sourceUrl':None,'placeEvidence':'user','attribution':None}
class EvidenceTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.path=Path(self.temp.name)/'db';self.store=Store(self.path);self.store.initialize([])
 def timeline(self):return {'places':{'p':copy.deepcopy(PLACE)},'days':[{'date':'2027-01-04','events':[{'id':'e','time':None,'placeId':'p','timeEvidence':'unknown','timeEvidenceNote':None}],'legs':[]}]}
 def test_global_coordinates_and_unknown_time_round_trip(self):
  value=self.timeline();validate_timeline(value);self.store.sync_trajectory(value)
  day=Store(self.path).get_trajectory_day('2027-01-04');self.assertEqual(day,value)
 def test_null_and_estimates_require_evidence(self):
  value=self.timeline();value['days'][0]['events'][0]['timeEvidence']='exact'
  with self.assertRaises(ValueError):validate_timeline(value)
  value['days'][0]['events'][0].update(time='12:00',timeEvidence='estimated')
  with self.assertRaises(ValueError):validate_timeline(value)
 def test_known_times_follow_saved_position(self):
  value=self.timeline();day=value['days'][0];day['events']=[{'id':'a','time':'13:00','placeId':'p','timeEvidence':'exact'},{'id':'b','time':'12:00','placeId':'p','timeEvidence':'exact'}]
  with self.assertRaises(ValueError):validate_timeline(value,require_complete=False)
 def test_user_chosen_transit_without_fare(self):
  value=self.timeline();day=value['days'][0];day['events'].append({'id':'b','time':None,'placeId':'p','timeEvidence':'unknown'})
  day['legs']=[{'fromEventId':'e','toEventId':'b','modeHint':'train','modeEvidence':'user'}]
  validate_timeline(value)
  day['legs'][0]['modeEvidence']='fare'
  with self.assertRaises(ValueError):validate_timeline(value)
 def test_migration_preserves_legacy_days_and_marks_evidence(self):
  import sqlite3
  path=Path(self.temp.name)/'legacy'
  with sqlite3.connect(path) as c:
   c.executescript((Path(__file__).parent/'fixtures/trajectory_legacy.sql').read_text())
   c.execute("INSERT INTO trajectory_places VALUES ('p','店','東京',139.7,35.6,'https://example.com')")
   c.execute("INSERT INTO trajectory_days VALUES ('2026-10-03')")
   c.execute("INSERT INTO trajectory_events VALUES ('a','2026-10-03',0,'12:00','p',NULL)")
   c.execute("INSERT INTO trajectory_events VALUES ('b','2026-10-03',1,'13:00','p',NULL)")
   c.execute("INSERT INTO trajectory_legs VALUES ('2026-10-03',0,'a','b','walk',NULL,1)")
   c.execute("INSERT INTO trajectory_leg_via_places VALUES ('2026-10-03',0,0,'p')")
  value=Store(path).get_trajectory_day('2026-10-03')
  self.assertEqual(value['places']['p']['placeEvidence'],'legacy')
  self.assertEqual([e['time'] for e in value['days'][0]['events']],['12:00','13:00'])
  self.assertEqual(value['days'][0]['legs'][0]['viaPlaceIds'],['p'])
  self.assertEqual(Store(path).get_trajectory_day('2026-10-03'),value)
  with sqlite3.connect(path) as c:self.assertEqual(c.execute('PRAGMA foreign_key_check').fetchall(),[])
 def test_estimated_transaction_time_cannot_claim_exact(self):
  from db.agent_store import AgentStore
  value=self.timeline();self.store.sync_trajectory(value)
  with self.store._connection() as c:
   Store._insert(c,{'id':'t','title':'支出','date':'2027-01-04T12:00','type':'income','category':'収入','amount':100,'timeEstimated':True})
  value['days'][0]['events'][0].update(time='12:00',timeEvidence='exact',transactionId='t')
  agent=AgentStore(self.path);thread=agent.create_thread()['id']
  with self.assertRaises(ValidationError):
   agent.create_proposal(thread,[{'kind':'trajectory.update','identity':{'kind':'day','date':'2027-01-04'},'data':{k:value['days'][0][k] for k in ('events','legs')}}])
