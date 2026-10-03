import copy,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from agent.trajectory import build_trajectory_context
from agent.runtime import AgentRunner
from db.store import Store,TrajectoryConflict
from db.agent_store import AgentStore
from services.validation import ValidationError
from test_trajectory_evidence import PLACE
from test_agent_runtime import ScriptModel
from langchain_core.messages import AIMessage
class TrajectoryAgentTests(unittest.IsolatedAsyncioTestCase):
 async def asyncSetUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.path=Path(self.temp.name)/'db';self.store=Store(self.path);self.store.initialize([])
  self.store.sync_trajectory({'places':{'p':PLACE},'days':[]})
  self.agent=AgentStore(self.path);self.thread=self.agent.create_thread()['id']
 def day_command(self,events,legs=None):return {'kind':'trajectory.create','identity':{'kind':'day','date':'2027-01-04'},'data':{'events':events,'legs':legs or []}}
 async def test_day_context_excludes_unrelated_transactions(self):
  for day in ['2027-01-04','2027-01-05']:self.store.create_transaction({'title':day,'date':day+'T12:00','type':'income','category':'収入','amount':100})
  with self.store._connection() as c:context=build_trajectory_context(c,'2027-01-04')
  self.assertEqual(len(context['transactions']),1);self.assertEqual(context['transactions'][0]['date'][:10],'2027-01-04')
 async def test_two_unknown_visits_require_order_confirmation(self):
  events=[{'id':name,'placeId':'p','time':None,'timeEvidence':'unknown'} for name in ['a','b']]
  proposal=self.agent.create_proposal(self.thread,[self.day_command(events,[{'fromEventId':'a','toEventId':'b','modeEvidence':'inferred','modeEvidenceNote':'時刻と移動手段は不明'}])])
  with self.assertRaises(TrajectoryConflict):self.store.apply_agent_proposal(proposal['id'],1)
  revised=self.agent.confirm_trajectory_order(proposal['id'],1)
  self.store.apply_agent_proposal(proposal['id'],revised['revision'])
 async def test_place_search_failure_keeps_revisable_proposal(self):
  from agent.place_http import PlaceProviderError
  command=self.day_command([{'id':'a','placeId':'unknown','time':None,'timeEvidence':'unknown'}])
  model=ScriptModel(replies=[AIMessage(content='',tool_calls=[{'name':'search_place','args':{'query':'店','place_id':'unknown'},'id':'1','type':'tool_call'}]),AIMessage(content='',tool_calls=[{'name':'edit_trajectory','args':{'operation':'create','identity':command['identity'],'data':command['data']},'id':'2','type':'tool_call'}]),AIMessage(content='座標を指定してください')])
  lease=self.agent.begin_turn(self.thread,'search-failure','軌跡を作成')
  context={'thread_id':self.thread,'client_message_id':'search-failure','run_token':lease['token']}
  with patch('agent.web_places.WebPlaceProvider.research',side_effect=PlaceProviderError('network')):
   result=await AgentRunner(self.store,model=model).run_turn(self.thread,[{'role':'user','text':'軌跡を作成'}],turn_context=context)
  proposal=self.agent.create_proposal(self.thread,result['commands'],place_candidates=result['placeCandidates'])
  self.assertIsNone(self.store.get_trajectory_day('2027-01-04'));self.assertEqual(proposal['metadata']['placeCandidates'][0]['candidates'],[])
  self.assertEqual(result['placeCandidates'][0]['status'],'error')
 async def test_same_transaction_not_assigned_twice(self):
  tx=self.store.create_transaction({'title':'給与','date':'2027-01-04T12:00','type':'income','category':'収入','amount':100})
  events=[{'id':name,'placeId':'p','time':None,'timeEvidence':'unknown','transactionId':tx['id']} for name in ['a','b']]
  with self.assertRaises(ValidationError):self.agent.create_proposal(self.thread,[self.day_command(events)])
 async def test_cross_date_edit_rolls_back_trajectory(self):
  tx=self.store.create_transaction({'title':'給与','date':'2027-01-04T12:00','type':'income','category':'収入','amount':100})
  self.store.sync_trajectory({'places':{'p':PLACE},'days':[{'date':'2027-01-04','events':[{'id':'a','placeId':'p','time':'12:00','timeEvidence':'exact','transactionId':tx['id']}],'legs':[]}]})
  with self.assertRaises(TrajectoryConflict):self.agent.create_proposal(self.thread,[{'kind':'transaction.update','identity':{'id':tx['id']},'data':{'title':'給与','date':'2027-01-05T12:00','type':'income','category':'収入','amount':100}}])
  self.assertEqual(self.store.get_transaction(tx['id'])['date'],'2027-01-04T12:00')
 async def test_fare_deletion_downgrades_leg_evidence(self):
  tx=self.store.create_transaction({'title':'運賃','date':'2027-01-04T12:00','type':'expense','category':'交通','merchant':'鉄道','amount':100,'paymentMethod':'e_money'})
  events=[{'id':name,'placeId':'p','time':time,'timeEvidence':'exact'} for name,time in [('a','12:00'),('b','13:00')]]
  self.store.sync_trajectory({'places':{'p':PLACE},'days':[{'date':'2027-01-04','events':events,'legs':[{'fromEventId':'a','toEventId':'b','modeHint':'train','modeEvidence':'fare','transportTransactionId':tx['id']}]}]})
  self.store.delete_transaction(tx['id'])
  leg=self.store.get_trajectory_day('2027-01-04')['days'][0]['legs'][0]
  self.assertEqual(leg['modeEvidence'],'inferred');self.assertTrue(leg['modeEvidenceNote']);self.assertNotIn('transportTransactionId',leg)
 async def test_cross_date_combined_edit_moves_reference_atomically(self):
  tx=self.store.create_transaction({'title':'給与','date':'2027-01-04T12:00','type':'income','category':'収入','amount':100})
  event={'id':'a','placeId':'p','time':'12:00','timeEvidence':'exact','transactionId':tx['id']}
  self.store.sync_trajectory({'places':{'p':PLACE},'days':[{'date':'2027-01-04','events':[event],'legs':[]}]})
  commands=[{'kind':'transaction.update','identity':{'id':tx['id']},'data':{'title':'給与','date':'2027-01-05T12:00','type':'income','category':'収入','amount':100}}, {'kind':'trajectory.update','identity':{'kind':'day','date':'2027-01-04'},'data':{'events':[],'legs':[]}}, {'kind':'trajectory.create','identity':{'kind':'day','date':'2027-01-05'},'data':{'events':[event],'legs':[]}}]
  proposal=self.agent.create_proposal(self.thread,commands)
  self.assertEqual(self.store.get_transaction(tx['id'])['date'],'2027-01-04T12:00')
  self.store.apply_agent_proposal(proposal['id'],1)
  self.assertEqual(self.store.get_trajectory_day('2027-01-04')['days'][0]['events'],[])
  self.assertEqual(self.store.get_trajectory_day('2027-01-05')['days'][0]['events'][0]['transactionId'],tx['id'])
