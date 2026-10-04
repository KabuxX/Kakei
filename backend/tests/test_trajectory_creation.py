import copy, sqlite3, sys, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from db.store import Store, TrajectoryConflict
from db.agent_store import AgentStore
from services.trajectory_creation import TrajectoryCreationService
from services.google_place_resolution import VisitResolution

def transaction(identifier,minute='12:00'):
    return {'id':identifier,'title':'合成店舗'+identifier,'date':'2027-03-01T'+minute,'type':'expense','category':'食費','amount':100,
        'merchant':'合成店舗'+identifier,'merchantAddress':'東京都千代田区二番町8-8','paymentMethod':'cash','items':[]}

class Resolver:
    def __init__(self, excluded=()):self.excluded=set(excluded)
    async def resolve_many(self,visits):
        import time
        return [VisitResolution(v.transaction_id,reason='ambiguous') if v.transaction_id in self.excluded else
            VisitResolution(v.transaction_id,'fixture-'+v.transaction_id,(139.7,35.6),time.time()) for v in visits]

class CreationTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.store=Store(Path(self.temp.name)/'db');self.store.initialize([transaction('a'),transaction('b','13:00'),transaction('c','14:00')])
        self.repo=AgentStore(self.store.db_path);self.thread=self.repo.create_thread()['id']

    async def complete(self,identifier='one',excluded=('c',)):
        lease=self.repo.begin_turn(self.thread,identifier,'2027年3月1日の取引で軌跡を作って')
        if 'cached' in lease:return lease['cached']
        prepared=await TrajectoryCreationService(self.store,Resolver(excluded)).prepare('2027-03-01')
        return self.repo.complete_turn(self.thread,identifier,lease,{'text':'保存する前の文章','preparedCreation':prepared})

    async def test_resolved_only_saved_without_proposal(self):
        before=self.store.list_transactions();response=await self.complete()
        self.assertIsNone(response['proposal'])
        self.assertEqual(response['trajectoryCreation']['counts'],{'saved':2,'existing':0,'excluded':1})
        self.assertEqual(response['trajectoryCreation']['excluded'][0]['transactionId'],'c')
        self.assertEqual(response['trajectoryCreation']['excluded'][0]['reason'],'ambiguous')
        self.assertEqual(self.store.list_transactions(),before)
        saved=self.store.get_trajectory_day('2027-03-01')['days'][0]
        self.assertEqual([e['transactionId'] for e in saved['events']],['a','b']);self.assertEqual(len(saved['legs']),1)
        self.assertEqual(self.repo.get_thread(self.thread)['messages'][-1]['trajectoryCreation'],response['trajectoryCreation'])
        self.assertNotIn('保存する前',response['message']['text'])

    async def test_all_excluded_preserves_day(self):
        await self.complete();before=self.store.get_trajectory_day('2027-03-01')
        response=await self.complete('two',('c',))
        self.assertEqual(response['trajectoryCreation']['counts'],{'saved':0,'existing':2,'excluded':1})
        self.assertEqual(self.store.get_trajectory_day('2027-03-01'),before)

    async def test_retry_existing_and_manual_visits(self):
        manual={'date':'2027-03-01','events':[{'id':'manual','time':'11:00','timeEvidence':'exact','placeId':'old'}],'legs':[]}
        self.store.sync_trajectory({'places':{'old':{'name':'手動','address':None,'coordinates':[139,35],'sourceUrl':None,'placeEvidence':'user'}},'days':[manual]})
        response=await self.complete();retry=await self.complete()
        self.assertEqual(response,retry)
        fresh=await self.complete('two')
        self.assertEqual(fresh['trajectoryCreation']['counts']['saved'],0)
        events=self.store.get_trajectory_day('2027-03-01')['days'][0]['events']
        self.assertEqual(len(events),3)
        for key,value in manual['events'][0].items():self.assertEqual(events[0][key],value)

    async def test_same_minute_and_unknown_manual_order(self):
        with self.store._connection() as connection:connection.execute("UPDATE transactions SET date='2027-03-01T12:00' WHERE id='b'")
        self.store.sync_trajectory({'places':{'old':{'name':'手動','address':None,'coordinates':[139,35],'sourceUrl':None,'placeEvidence':'user'}},'days':[
            {'date':'2027-03-01','events':[{'id':'manual','time':None,'timeEvidence':'unknown','placeId':'old'}],'legs':[]}]})
        await self.complete()
        events=self.store.get_trajectory_day('2027-03-01')['days'][0]['events']
        self.assertEqual([e['id'] if 'transactionId' not in e else e['transactionId'] for e in events],['a','b','manual'])
        self.assertEqual([e['time'] for e in events],['12:00','12:00',None])

    async def test_atomic_reply_rollback_and_stale_token(self):
        lease=self.repo.begin_turn(self.thread,'one','軌跡を作って')
        prepared=await TrajectoryCreationService(self.store,Resolver()).prepare('2027-03-01')
        with self.store._connection() as connection:
            connection.execute("CREATE TRIGGER fail_reply BEFORE INSERT ON agent_messages WHEN NEW.role='assistant' BEGIN SELECT RAISE(ABORT,'injected'); END")
        with self.assertRaises(sqlite3.Error):self.repo.complete_turn(self.thread,'one',lease,{'text':'準備済み','preparedCreation':prepared})
        self.assertEqual(self.store.list_trajectory_dates(),[])
        with self.store._connection() as connection:
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM google_place_coordinates').fetchone()[0],0)
            connection.execute('DROP TRIGGER fail_reply')
        with self.assertRaises(TrajectoryConflict):self.repo.complete_turn(self.thread,'one',{**lease,'token':'stale'},{'text':'準備済み','preparedCreation':prepared})
        self.assertEqual(self.store.list_trajectory_dates(),[])

    async def test_more_than_one_hundred_records_and_source_conflict(self):
        for i in range(101):self.store.create_transaction({k:v for k,v in transaction('extra',f'{i//60:02}:{i%60:02}').items() if k!='id'})
        prepared=await TrajectoryCreationService(self.store,Resolver()).prepare('2027-03-01')
        self.assertEqual(prepared.result['counts']['saved'],104)
        lease=self.repo.begin_turn(self.thread,'many','軌跡を作って')
        self.store.create_transaction({k:v for k,v in transaction('more').items() if k!='id'})
        with self.assertRaises(TrajectoryConflict):self.repo.complete_turn(self.thread,'many',lease,{'text':'準備済み','preparedCreation':prepared})
        self.assertEqual(self.store.list_trajectory_dates(),[])

    async def test_expired_turn_cannot_save(self):
        import time
        from agent.limits import TURN_LEASE_SECONDS
        lease=self.repo.begin_turn(self.thread,'expired','軌跡を作って')
        prepared=await TrajectoryCreationService(self.store,Resolver()).prepare('2027-03-01')
        with self.store._connection() as connection:
            connection.execute('UPDATE agent_turns SET started_at=? WHERE thread_id=?',(time.time()-TURN_LEASE_SECONDS-1,self.thread))
        with self.assertRaises(TrajectoryConflict):self.repo.complete_turn(self.thread,'expired',lease,{'text':'準備済み','preparedCreation':prepared})
        self.assertEqual(self.store.list_trajectory_dates(),[])
