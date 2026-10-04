import asyncio,copy,json,sys,tempfile,time,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from agent.place_search import SearchBudget
from geolonia_fixtures import DETAILED_RESULT,ADDRESS

class ClientTests(unittest.IsolatedAsyncioTestCase):
    def factory(self,**kwargs):
        try:from agent.geolonia_client import GeoloniaClient
        except ImportError:self.fail('bounded Geolonia subprocess client is missing')
        client=GeoloniaClient(**kwargs);self.addAsyncCleanup(client.close);return client

    async def asyncSetUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.worker=Path(self.tmp.name)/'worker.py'
        self.worker.write_text('import json,sys\nfor line in sys.stdin:\n r=json.loads(line)\n print(json.dumps({"id":r["id"],"status":"ok",**'+repr(DETAILED_RESULT)+',"libraryVersion":"3.1.3","bytesRead":100}),flush=True)\n')
        self.budget=SearchBudget(time.monotonic()+180);self.addAsyncCleanup(self.budget.close)

    async def test_no_node_or_dependency_is_unavailable(self):
        client=self.factory(executable='/missing/node')
        result=await client.session('x',self.budget).lookup(ADDRESS,grounded_prefixes=[])
        self.assertEqual(result['status'],'unavailable')
        self.worker.write_text('import sys\nsys.stderr.write("ERR_MODULE_NOT_FOUND")\nsys.exit(1)\n')
        client=self.factory(executable=sys.executable,worker_path=self.worker)
        self.assertEqual((await client.session('x',self.budget).lookup(ADDRESS,grounded_prefixes=[]))['status'],'unavailable')

    async def test_bad_stdout_size_or_id_is_failed(self):
        for output in ('not JSON',json.dumps({'id':'wrong','status':'ok'}),'x'*70000):
            self.worker.write_text('import sys\nfor line in sys.stdin: print('+repr(output)+',flush=True)\n')
            client=self.factory(executable=sys.executable,worker_path=self.worker)
            result=await client.session(output[:10],self.budget).lookup(ADDRESS,grounded_prefixes=[])
            self.assertEqual(result['status'],'failed')
            self.assertIn('geolonia_invalid_response',result['unresolved'])

    async def test_cancel_kills_and_reaps_worker(self):
        ready=Path(self.tmp.name)/'pid'
        self.worker.write_text('import os,time\nfrom pathlib import Path\nPath('+repr(str(ready))+').write_text(str(os.getpid()))\ntime.sleep(60)\n')
        client=self.factory(executable=sys.executable,worker_path=self.worker)
        session=client.session('x',self.budget)
        task=asyncio.create_task(session.lookup(ADDRESS,grounded_prefixes=[]))
        while not ready.exists():
            if task.done():self.fail(str(await task))
            await asyncio.sleep(.005)
        pid=int(ready.read_text());task.cancel()
        with self.assertRaises(asyncio.CancelledError):await task
        import os
        with self.assertRaises(ProcessLookupError):os.kill(pid,0)

    async def test_six_variants_and_thirty_seconds_are_shared(self):
        client=self.factory(executable=sys.executable,worker_path=self.worker)
        session=client.session('x',self.budget)
        first=await session.lookup(ADDRESS,grounded_prefixes=[])
        self.assertEqual(first['status'],'matched')
        again=await session.lookup(ADDRESS,grounded_prefixes=[])
        self.assertEqual(first,again)
        # Six distinct unsupported addresses use up the session, not per-address limits.
        for n in range(5):await session.lookup(f'東京都文京区本郷1-2-{n+10}',grounded_prefixes=[])
        last=await session.lookup('東京都文京区本郷1-2-99',grounded_prefixes=[])
        self.assertIn('geolonia_variant_limit',last['unresolved'])
        clock=[0.0];timed=self.factory(executable=sys.executable,worker_path=self.worker,clock=lambda:clock[0])
        timed_session=timed.session('clock',SearchBudget(180,clock=lambda:clock[0]))
        self.worker.write_text('import sys,time\nfor line in sys.stdin:\n time.sleep(.05)\n print("not JSON",flush=True)\n')
        task=asyncio.create_task(timed_session.lookup(ADDRESS,grounded_prefixes=[]))
        await asyncio.sleep(.01);clock[0]=31
        await task
        result=await timed_session.lookup('東京都文京区本郷2-2-3',grounded_prefixes=[])
        self.assertIn('geolonia_time_limit',result['unresolved'])

    async def test_web_reserve_and_process_slots(self):
        client=self.factory(executable=sys.executable,worker_path=self.worker)
        late=SearchBudget(50,clock=lambda:20)
        result=await client.session('late',late).lookup(ADDRESS,grounded_prefixes=[])
        self.assertEqual(result['status'],'skipped')
        self.assertIn('geolonia_time_limit',result['unresolved'])
        self.assertEqual(late.counts['web'],0)
        sessions=[client.session(str(n),self.budget) for n in range(3)]
        outputs=await asyncio.gather(*(s.lookup(ADDRESS,grounded_prefixes=[]) for s in sessions[:2]))
        self.assertTrue(all(o['status']=='matched' for o in outputs))
        pending=asyncio.create_task(sessions[2].lookup(ADDRESS,grounded_prefixes=[]))
        await asyncio.sleep(.01);self.assertFalse(pending.done())
        await sessions[0].close()
        self.assertEqual((await pending)['status'],'matched')
        # Idle Web time does not consume Geolonia's allowance.
        clock=[0.0];local=self.factory(executable=sys.executable,worker_path=self.worker,clock=lambda:clock[0])
        s=local.session('idle',SearchBudget(180,clock=lambda:clock[0]))
        await s.lookup(ADDRESS,grounded_prefixes=[]);clock[0]=40
        self.assertNotIn('geolonia_time_limit',(await s.lookup('東京都文京区本郷1-2-8',grounded_prefixes=[]))['unresolved'])

    async def test_queued_address_does_not_renew_session_allowance(self):
        ready=Path(self.tmp.name)/'ready'
        self.worker.write_text('import json,sys,time\nfrom pathlib import Path\nfor line in sys.stdin:\n r=json.loads(line)\n Path('+repr(str(ready))+').write_text("ready")\n time.sleep(.05)\n print(json.dumps({"id":r["id"],"status":"ok",**'+repr(DETAILED_RESULT)+',"libraryVersion":"3.1.3","bytesRead":100}),flush=True)\n')
        clock=[0.0];client=self.factory(executable=sys.executable,worker_path=self.worker,clock=lambda:clock[0])
        session=client.session('queued',SearchBudget(180,clock=lambda:clock[0]))
        first=asyncio.create_task(session.lookup(ADDRESS,grounded_prefixes=[]))
        while not ready.exists():await asyncio.sleep(.002)
        second=asyncio.create_task(session.lookup(ADDRESS+' テストビル',grounded_prefixes=[]))
        await asyncio.sleep(.005);clock[0]=21
        self.assertEqual((await first)['status'],'matched')
        self.assertIn('geolonia_time_limit',(await second)['unresolved'])
