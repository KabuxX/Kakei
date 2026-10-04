import copy,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from geolonia_fixtures import DETAILED_RESULT,COARSE_RESULT,GEOLONIA_PLACE,ADDRESS

class CandidateTests(unittest.TestCase):
    def test_candidate_preserves_grounded_address_and_sources(self):
        try:from agent.geolonia_candidates import candidate_from_match
        except ImportError:self.fail('Geolonia candidate conversion is missing')
        store={'name':'合成テスト店舗','address':ADDRESS,'sources':[]}
        result={**copy.deepcopy(DETAILED_RESULT),'status':'matched','originalAddress':ADDRESS,'matchedVariant':{'address':ADDRESS,'strategies':['original']},'libraryVersion':'3.1.3'}
        candidate=candidate_from_match(store,result)
        self.assertEqual(candidate['address'],ADDRESS)
        self.assertEqual(candidate['coordinates'],[139.7,35.7])
        self.assertEqual(candidate['coordinateEvidence']['verification'],'needs_confirmation')
        self.assertEqual(candidate['coordinateEvidence']['addressMatch']['record'],GEOLONIA_PLACE['coordinateEvidence']['addressMatch']['record'])
        self.assertIsNone(candidate_from_match(store,{**result,'status':'coarse',**COARSE_RESULT}))
        self.assertIsNone(candidate_from_match(store,{**result,'proof':{'fetches':[],'observation':None}}))
        wrong={**result,'match':{**result['match'],'addr':'2-4'}}
        self.assertIsNone(candidate_from_match(store,wrong))
