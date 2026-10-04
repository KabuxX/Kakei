"""Synthetic fixtures reproduce the October 1 live-search failure modes."""
import copy,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import test_agent_place_search as web_tests
from web_place_fixtures import ADDRESS

class SearchRecoveryTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):await web_tests.SearchTests.asyncSetUp(self)
    async def asyncTearDown(self):await self.budget.close()

    def grounded_address(self,**values):
        self.resolver.messages=[{'id':'u','role':'user','text':ADDRESS}]
        return {'place_id':'p','address':ADDRESS,'evidence':[{'field':'address','source':'user_message','source_id':'u','value':ADDRESS}],**values}

    async def test_historical_warning_does_not_block_current_coordinate_verification(self):
        warning='2026年10月1日時点の所在履歴は未確認。'
        self.provider.rows[0]['warnings']=[{'kind':'historical_location_unconfirmed','note':warning}]
        self.resolver.messages=[{'id':'u','role':'user','text':'2026年10月1日の軌跡'}]
        request={**self.req,'visit_date':'2026-10-01','evidence':[{'field':'visit_date','source':'user_message','source_id':'u','value':'2026-10-01'}]}
        out=await self.service.search(request)
        self.assertEqual(len(out['candidates']),1)
        self.assertIn(warning,out['candidates'][0]['coordinateEvidence']['note'])
        self.assertIn('訪問日2026-10-01当時の所在地は未確認',out['candidates'][0]['coordinateEvidence']['note'])

    async def test_identity_uncertainty_still_blocks_candidates(self):
        self.provider.rows[0]['unresolved']=['別支店の可能性がある。']
        out=await self.service.search(self.req)
        self.assertEqual(out['candidates'],[])
        self.assertIn('別支店の可能性がある。',out['unlocatedCandidates'][0]['unresolved'])

    async def test_limit_keeps_discovered_store_and_citation(self):
        async def no_coordinates(*args,**kwargs):return {'candidates':[],'anchors':[],'verifiedHints':[],'unresolved':['position_unverified'],'pages':[]}
        self.verifier.verify=no_coordinates
        self.budget.counts['web']=5
        out=await self.service.search(self.req)
        self.assertEqual(out['status'],'partial')
        self.assertEqual(len(out['unlocatedCandidates']),1)
        self.assertEqual(out['unlocatedCandidates'][0]['name'],'ドトールコーヒーショップ 西鉄福岡駅店')
        self.assertTrue(out['sources'])
        self.assertIn('request_limit',out['unresolved'])

    async def test_familymart_language_variant_with_grounded_address_can_be_verified(self):
        self.provider.rows[0].update(name='ファミリーマート一の橋店',branch='一の橋店')
        out=await self.service.search(self.grounded_address(query='FamilyMart',brand='FamilyMart'))
        self.assertEqual(len(out['candidates']),1)
        self.assertEqual(out['candidates'][0]['name'],'ファミリーマート一の橋店')

    async def test_other_brand_at_same_address_remains_excluded(self):
        self.provider.rows[0].update(name='ローソン一の橋店',branch='一の橋店')
        out=await self.service.search(self.grounded_address(query='FamilyMart',brand='FamilyMart'))
        self.assertEqual(out['candidates'],[])
        self.assertIn('name_mismatch',out['unlocatedCandidates'][0]['unresolved'])

    async def test_abbreviated_branch_at_exact_address_keeps_confirmation_notice(self):
        self.provider.rows[0].update(name='セブン‐イレブン 千代田二番町店',branch='千代田二番町店')
        out=await self.service.search(self.grounded_address(query='セブン-イレブン 千代田店',brand='セブン-イレブン',branch='千代田店'))
        self.assertEqual(len(out['candidates']),1)
        candidate=out['candidates'][0]
        self.assertIn('branch_unconfirmed',candidate['matchReasons'])
        self.assertIn('入力の支店名',candidate['coordinateEvidence']['note'])
        self.assertEqual(candidate['coordinateEvidence']['verification'],'needs_confirmation')

    async def test_abbreviated_branch_without_exact_address_remains_excluded(self):
        self.provider.rows[0].update(name='セブン-イレブン 千代田二番町店',branch='千代田二番町店')
        out=await self.service.search({'query':'セブン-イレブン 千代田店','brand':'セブン-イレブン','branch':'千代田店','place_id':'p'})
        self.assertEqual(out['candidates'],[])
        self.assertIn('branch_unconfirmed',out['unlocatedCandidates'][0]['unresolved'])

    async def test_different_branch_at_same_address_remains_excluded(self):
        self.provider.rows[0].update(name='セブン-イレブン 麹町駅前店',branch='麹町駅前店')
        out=await self.service.search(self.grounded_address(query='セブン-イレブン 千代田店',brand='セブン-イレブン',branch='千代田店'))
        self.assertEqual(out['candidates'],[])
        self.assertIn('branch_unconfirmed',out['unlocatedCandidates'][0]['unresolved'])

    async def test_building_relation_warning_does_not_block_published_store_pin(self):
        warning='建物・施設との関係は確定できない。'
        self.provider.rows[0]['warnings']=[{'kind':'building_relation_unconfirmed','note':warning}]
        out=await self.service.search(self.req)
        self.assertEqual(len(out['candidates']),1)
        self.assertIn(warning,out['candidates'][0]['coordinateEvidence']['note'])

    async def test_branch_warning_is_not_dependent_on_model_wording(self):
        warning='入力の「千代田店」と店名が完全一致しないため、調査文では該当候補として示されています。'
        self.provider.rows[0].update(name='セブン-イレブン 千代田二番町店',branch='千代田二番町店',warnings=[{'kind':'branch_label_difference','note':warning}])
        out=await self.service.search(self.grounded_address(query='セブン-イレブン 千代田店',brand='セブン-イレブン',branch='千代田店'))
        self.assertEqual(len(out['candidates']),1)
        self.assertIn(warning,out['candidates'][0]['coordinateEvidence']['note'])

    async def test_brand_variants_with_conflicting_coordinates_remain_flagged(self):
        from agent.place_search import compare_candidates
        from coordinate_fixtures import PUBLISHED_PLACE
        first={**copy.deepcopy(PUBLISHED_PLACE),'name':'FamilyMart 一の橋店'}
        second={**copy.deepcopy(PUBLISHED_PLACE),'name':'ファミリーマート一の橋店','coordinates':[130.5,33.59]}
        candidates=compare_candidates([first,second])
        self.assertEqual(len(candidates),2)
        self.assertTrue(all('coordinate_conflict' in c['matchReasons'] for c in candidates))
