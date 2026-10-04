import copy
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from geolonia_fixtures import DETAILED_RESULT


class AddressTests(unittest.TestCase):
    def functions(self):
        try:
            from agent.geolonia_addresses import eligible_address, address_variants, match_reasons
        except ImportError:
            self.fail('Geolonia address eligibility and retry functions are missing')
        return eligible_address,address_variants,match_reasons

    def test_variants_preserve_numbers_and_deduplicate(self):
        _,variants,_=self.functions()
        rows=variants('日本 〒113-0033 東京都文京区本郷１丁目２番３号 テストビル 10階',grounded_prefixes=[])
        values=[r['address'] for r in rows]
        self.assertLessEqual(len(rows),6);self.assertEqual(len(values),len(set(values)))
        self.assertIn('東京都文京区本郷1-2-3',values)
        self.assertTrue(all('３' in s or '3' in s for s in values))

    def test_floor_and_room_never_erase_address_suffix(self):
        _,variants,_=self.functions()
        values=[v['address'] for v in variants('東京都文京区本郷1-2-301',grounded_prefixes=[])]
        self.assertTrue(all('301' in s for s in values))
        separated=[v['address'] for v in variants('東京都文京区本郷1-2 テストビル301号室',grounded_prefixes=[])]
        self.assertIn('東京都文京区本郷1-2',separated)

    def test_prefix_only_uses_grounded_administrative_values(self):
        _,variants,_=self.functions()
        address='文京区本郷1-2-3'
        self.assertFalse(any(v['address'].startswith('東京都') for v in variants(address,grounded_prefixes=[])))
        self.assertIn('東京都文京区本郷1-2-3',[v['address'] for v in variants(address,grounded_prefixes=['東京都'])])
        self.assertNotIn('東京駅文京区本郷1-2-3',[v['address'] for v in variants(address,grounded_prefixes=['東京駅'])])

    def test_detailed_match_checks_both_levels_and_other(self):
        _,_,reasons=self.functions()
        original='東京都文京区本郷1-2-3';variant={'address':original,'strategies':['original']}
        match=copy.deepcopy(DETAILED_RESULT['match'])
        self.assertEqual(reasons(original,variant,match),[])
        for patch in ({'level':3},{'point':{'lng':139.7,'lat':35.7,'level':3}},{'addr':'2-4'},{'other':'-9'},{'point':{'lng':True,'lat':35.7,'level':8}}):
            with self.subTest(patch=patch):self.assertTrue(reasons(original,variant,{**match,**patch}))

    def test_non_japan_and_name_only_are_ineligible(self):
        eligible,_,_=self.functions()
        self.assertFalse(eligible('テスト珈琲店',None))
        self.assertFalse(eligible('東京都文京区本郷1-2-3','us'))
        self.assertTrue(eligible('東京都文京区本郷1-2-3',None))
        self.assertTrue(eligible('東京都文京区本郷',None))
