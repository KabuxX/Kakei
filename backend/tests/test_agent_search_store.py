import json, sys, tempfile, time, unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from db.agent_search_store import AgentSearchStore
from db.agent_store import AgentStore
from db.store import TrajectoryConflict, TrajectoryNotFound
from services.agent_places import source_version
from agent_search_fixtures import active_turn, REQUEST, result

class SearchStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name)/'db'
        self.store, self.agent, self.ctx = active_turn(self.path)
        self.searches = AgentSearchStore(self.path)
        self.thread = self.ctx['thread_id']

    def test_search_survives_no_proposal_and_model_failure(self):
        sid = self.searches.start(self.ctx, REQUEST)
        self.searches.finish(self.ctx, sid, result(sid))
        self.agent.fail_turn(self.thread, 'one', self.ctx['run_token'])
        self.assertEqual(AgentSearchStore(self.path).get(self.thread, sid)['result']['status'], 'empty')
        self.assertEqual(self.agent.get_thread(self.thread)['proposals'], [])

    def test_old_token_cannot_overwrite_retry(self):
        sid = self.searches.start(self.ctx, REQUEST)
        self.searches.record_attempt(self.ctx, sid, {'id':'a','stage':'formal','status':'running'})
        self.agent.fail_turn(self.thread, 'one', self.ctx['run_token'])
        lease = self.agent.begin_turn(self.thread, 'one', '軌跡を作成')
        self.assertEqual(self.searches.get(self.thread, sid)['attempts'][0]['status'], 'cancelled')
        with self.assertRaises(TrajectoryConflict): self.searches.finish(self.ctx, sid, result(sid))
        newer = {**self.ctx, 'run_token':lease['token']}
        other = self.searches.start(newer, REQUEST)
        self.assertNotEqual(sid, other)
        self.assertEqual(len(self.searches.history(self.thread)['records']), 2)

    def test_history_pagination_and_utf8_bounds(self):
        with patch('db.agent_search_store.time.time', return_value=123):
            ids = [self.searches.start(self.ctx, REQUEST) for _ in range(12)]
        for sid in ids:
            candidates = [{'id': str(i), 'name':'あ'*2000,'address':'い'*2000,'coordinates':[130,33]} for i in range(20)]
            self.searches.record_attempt(self.ctx, sid, {'id':'a','stage':'nearby','status':'complete','candidates':candidates})
            self.searches.finish(self.ctx, sid, result(sid, candidates))
        seen=[]; cursor=None
        while True:
            page=self.searches.history(self.thread, before_id=cursor, limit=10)
            self.assertLessEqual(len(json.dumps(page, ensure_ascii=False).encode()), 32768)
            seen.extend(r['searchId'] for r in page['records'])
            if not page['hasMore']: break
            self.assertNotEqual(cursor, page['nextBeforeId']); cursor=page['nextBeforeId']
        self.assertEqual(set(seen),set(ids)); self.assertEqual(len(seen),12)
        self.assertLessEqual(len(json.dumps(self.searches.summary(self.thread), ensure_ascii=False).encode()),8192)
        rec=self.searches.get(self.thread, ids[0])
        for c in rec['result']['candidates']:
            self.assertLessEqual(len(json.dumps(c, ensure_ascii=False).encode()),8192)
        self.assertTrue(rec['result']['truncated'])

    def test_delete_during_search_does_not_resurrect(self):
        sid=self.searches.start(self.ctx,REQUEST)
        self.agent.delete_thread(self.thread)
        with self.assertRaises(TrajectoryConflict): self.searches.finish(self.ctx,sid,result(sid))
        with self.store._connection() as c: self.assertEqual(c.execute('SELECT COUNT(*) FROM agent_place_searches').fetchone()[0],0)

    def test_scope_stale_recovery_and_source_version(self):
        with self.store._connection() as c: before=source_version(c)
        sid=self.searches.start(self.ctx,REQUEST)
        other=self.agent.create_thread()['id']
        with self.assertRaises(TrajectoryNotFound): self.searches.get(other,sid)
        with self.assertRaises(TrajectoryNotFound): self.searches.history(other,before_id=sid)
        with self.store._connection() as c:
            self.assertEqual(source_version(c),before)
            c.execute('UPDATE agent_turns SET started_at=?',(time.time()-131,))
        AgentStore(self.path)
        self.assertEqual(self.searches.get(self.thread,sid)['status'],'cancelled')

    def test_legacy_history_and_schema_upgrade(self):
        from test_agent_places import COMMAND, CANDIDATE
        proposal=self.agent.create_proposal(self.thread,[COMMAND],place_candidates=[{'placeId':'p','query':'旧検索','candidates':[CANDIDATE]}])
        history=self.searches.history(self.thread)
        self.assertEqual(history['records'][0]['source'],'legacy_proposal')
        self.assertIsNone(history['records'][0]['searchId'])
        self.assertEqual(history['records'][0]['proposalId'],proposal['id'])
        with self.store._connection() as c: c.execute('DROP TABLE agent_place_searches')
        AgentSearchStore(self.path)
        self.assertEqual(self.searches.history(self.thread)['records'][0]['proposalId'],proposal['id'])

    def test_selectable_names_are_not_shortened_to_meet_byte_limit(self):
        import uuid
        sid=self.searches.start(self.ctx,REQUEST)
        candidate={'id':str(uuid.uuid4()),'providerId':'x'*8500,'name':'カ'*190+'西鉄福岡駅店','address':'a'*500,'attribution':'a'*200,'sourceUrl':'https://example.com/'+'p'*100,'coordinates':[130.4,33.59],'matchReasons':['name_and_region_match'],'searchId':sid}
        self.assertGreater(len(json.dumps(candidate,ensure_ascii=False).encode()),8192)
        self.searches.finish(self.ctx,sid,result(sid,[candidate]))
        saved=self.searches.get(self.thread,sid)['result']
        self.assertTrue(saved['truncated'])
        for c in saved['candidates']:
            self.assertEqual(c['name'],candidate['name'])
        self.assertEqual(saved['candidates'],[])
        self.assertEqual(saved['omittedCandidates'],1)

    def test_bounds_preserve_source_identity(self):
        from web_place_fixtures import PLACE,SOURCE
        sid=self.searches.start(self.ctx,REQUEST)
        candidate={**PLACE,'id':'c','sources':[{**SOURCE,'url':'https://store.example/'+'あ'*900}]}
        self.searches.finish(self.ctx,sid,result(sid,[candidate]))
        saved=self.searches.get(self.thread,sid)['result']['candidates']
        self.assertEqual(saved[0]['sources'][0]['url'],candidate['sources'][0]['url'])
