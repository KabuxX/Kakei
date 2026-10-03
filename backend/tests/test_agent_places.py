import json,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import httpx
from agent.places import search_places
from api.http import HTTPFailure
from db.store import Store,TrajectoryConflict
from db.agent_store import AgentStore
from services.validation import ValidationError

CANDIDATE={'id':'candidate-a','name':'同名店','address':'New York','coordinates':[-73.9,40.7],'sourceUrl':'https://www.openstreetmap.org/copyright','attribution':'© OpenStreetMap contributors'}
COMMAND={'kind':'trajectory.create','identity':{'kind':'day','date':'2027-01-04'},'data':{'events':[{'id':'e','time':None,'timeEvidence':'unknown','placeId':'unknown-store'}],'legs':[]}}
class PlacesTests(unittest.TestCase):
 def test_requests_japanese_and_preserves_provider_names_addresses_and_coordinates(self):
  def handle(request):
   self.assertEqual(request.url.params.get('lang'),'ja')
   self.assertEqual(request.url.params['text'],'東京駅')
   self.assertEqual(request.url.params['bias'],'proximity:139.767,35.681')
   return httpx.Response(200,json={'results':[
    {'name':'東京駅','formatted':'日本、東京都千代田区丸の内','lon':139.767,'lat':35.681},
    {'name':'Tokyo Station','formatted':'Tokyo, Japan','lon':139.768,'lat':35.682}]})
  with patch.dict('os.environ',{'GEOAPIFY_API_KEY':'secret'}),httpx.Client(transport=httpx.MockTransport(handle)) as client:
   result=search_places('東京駅',bias=[139.767,35.681],client=client)
  self.assertEqual(result[0]['name'],'東京駅')
  self.assertEqual(result[0]['address'],'日本、東京都千代田区丸の内')
  self.assertEqual(result[0]['coordinates'],[139.767,35.681])
  self.assertEqual(result[1]['name'],'Tokyo Station')
  self.assertEqual(result[1]['address'],'Tokyo, Japan')
 def test_geoapify_search_returns_distinct_same_name_results(self):
  requests=[]
  def handle(request):
   requests.append(request)
   return httpx.Response(200,json={'results':[{'place_id':str(i),'name':'同名店','formatted':city,'lon':lon,'lat':40,'datasource':{'url':'https://www.openstreetmap.org/copyright','attribution':'OSM'}} for i,city,lon in [(1,'New York',-73),(2,'London',0)]]})
  with patch.dict('os.environ',{'GEOAPIFY_API_KEY':'secret'}),httpx.Client(transport=httpx.MockTransport(handle)) as client:
   result=search_places('同名店',client=client)
  self.assertEqual(len(result),2);self.assertNotEqual(result[0]['id'],result[1]['id']);self.assertNotIn('secret',json.dumps(result));self.assertEqual(requests[0].url.params['limit'],'5')
 def test_timeout_empty_and_missing_key(self):
  with patch.dict('os.environ',{},clear=True),self.assertRaises(HTTPFailure):search_places('店')
  def timeout(request):raise httpx.ReadTimeout('timeout')
  with patch.dict('os.environ',{'GEOAPIFY_API_KEY':'secret'}),httpx.Client(transport=httpx.MockTransport(timeout)) as client,self.assertRaises(HTTPFailure):search_places('店',client=client)
  with patch.dict('os.environ',{'GEOAPIFY_API_KEY':'secret'}),httpx.Client(transport=httpx.MockTransport(lambda r:httpx.Response(200,json={'results':[]}))) as client:self.assertEqual(search_places('店',client=client),[])
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
