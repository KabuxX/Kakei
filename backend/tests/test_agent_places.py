import json,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import httpx
from api.http import HTTPFailure
from db.store import Store,TrajectoryConflict
from db.agent_store import AgentStore
from services.validation import ValidationError

CANDIDATE={'id':'candidate-a','name':'同名店','address':'New York','coordinates':[-73.9,40.7],'sourceUrl':'https://www.openstreetmap.org/copyright','attribution':'© OpenStreetMap contributors'}
COMMAND={'kind':'trajectory.create','identity':{'kind':'day','date':'2027-01-04'},'data':{'events':[{'id':'e','time':None,'timeEvidence':'unknown','placeId':'unknown-store'}],'legs':[]}}
class PlacesTests(unittest.TestCase):
 def test_candidate_selection_uses_saved_coordinates_and_rejects_forgery(self):
  with tempfile.TemporaryDirectory() as directory:
   path=Path(directory)/'db';store=Store(path);store.initialize([]);agent=AgentStore(path);thread=agent.create_thread()['id']
   proposal=agent.create_proposal(thread,[COMMAND],place_candidates=[{'placeId':'unknown-store','query':'同名店','candidates':[CANDIDATE]}])
   with self.assertRaises(TrajectoryConflict):store.apply_agent_proposal(proposal['id'],1)
   with self.assertRaises(ValidationError):agent.select_place_candidate(proposal['id'],1,'forged')
   selected=agent.select_place_candidate(proposal['id'],1,'candidate-a')
   self.assertEqual(selected['revision'],2)
   with self.assertRaises(TrajectoryConflict):agent.select_place_candidate(proposal['id'],1,'candidate-a')
   store.apply_agent_proposal(proposal['id'],2)
   self.assertEqual(store.get_trajectory_day('2027-01-04')['places']['unknown-store']['coordinates'],CANDIDATE['coordinates'])
 def test_reselection_preserves_edits_and_resolves_saved_place_without_duplicates(self):
  with tempfile.TemporaryDirectory() as directory:
   path=Path(directory)/'db';store=Store(path);store.initialize([]);agent=AgentStore(path);thread=agent.create_thread()['id']
   saved={k:CANDIDATE[k] for k in ('name','address','coordinates','sourceUrl','attribution')};saved['placeEvidence']='provider'
   store.sync_trajectory({'places':{'saved':saved},'days':[]})
   candidates=[CANDIDATE,{**CANDIDATE,'id':'candidate-b','coordinates':[0,51],'address':'London'},{**CANDIDATE,'id':'saved-choice','savedPlaceId':'saved'}]
   p=agent.create_proposal(thread,[COMMAND],place_candidates=[{'placeId':'unknown-store','query':'store','candidates':candidates}])
   p=agent.select_place_candidate(p['id'],p['revision'],'candidate-a')
   p=agent.select_place_candidate(p['id'],p['revision'],'candidate-b')
   self.assertEqual(p['after'][1]['coordinates'],[0,51]);self.assertEqual(len(p['commands']),2)
   p=agent.select_place_candidate(p['id'],p['revision'],'saved-choice')
   self.assertEqual(len(p['commands']),1);self.assertEqual(p['after'][0]['events'][0]['placeId'],'saved')
   commands=p['commands'];commands[0]['data']['events'][0].update(time='10:00',timeEvidence='exact')
   p=agent.revise_proposal(p['id'],p['revision'],commands)
   p=agent.select_place_candidate(p['id'],p['revision'],manual={'name':'Manual','coordinates':[140,36]},place_id='unknown-store')
   self.assertEqual(p['after'][0]['events'][0]['time'],'10:00')
   p=agent.select_place_candidate(p['id'],p['revision'],'saved-choice')
   store.apply_agent_proposal(p['id'],p['revision'])
   day=store.get_trajectory_day('2027-01-04')
   self.assertEqual(day['days'][0]['events'][0]['placeId'],'saved')
   self.assertNotIn('unknown-store',day['places'])
 def test_review_candidate_requires_confirmation_and_keeps_provenance(self):
  from web_place_fixtures import PLACE
  with tempfile.TemporaryDirectory() as directory:
   path=Path(directory)/'db';store=Store(path);store.initialize([]);agent=AgentStore(path);thread=agent.create_thread()['id']
   candidate={**PLACE,'id':'review','geocoding':{**PLACE['geocoding'],'verification':'needs_confirmation','matchCode':{'address_number':'unmatched'}}}
   p=agent.create_proposal(thread,[COMMAND],place_candidates=[{'placeId':'unknown-store','query':'店舗','candidates':[candidate]}])
   for confirmed in (False,'true',1):
    with self.assertRaises(ValidationError):agent.select_place_candidate(p['id'],1,'review',confirmed=confirmed)
   p=agent.select_place_candidate(p['id'],1,'review',confirmed=True)
   store.apply_agent_proposal(p['id'],p['revision'])
   saved=store.get_trajectory_day('2027-01-04')['places']['unknown-store']
   self.assertEqual(saved['geocoding']['verification'],'user_confirmed')
   self.assertEqual(saved['geocoding']['matchCode']['address_number'],'unmatched')
   self.assertEqual(saved['coordinates'],PLACE['coordinates'])
