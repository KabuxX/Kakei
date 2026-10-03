import copy,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from agent.coordinate_estimation import estimate_coordinates
from services.coordinate_math import destination,meters_between
from services.coordinate_evidence import validate_coordinate_evidence
from services.validation import ValidationError
from coordinate_fixtures import STORE_ROW,BUILDING_HINT,ANCHOR

def row(hint):return {**copy.deepcopy(STORE_ROW),'verifiedHints':[hint]}
class EstimateTests(unittest.TestCase):
    def test_english_relationships_keep_the_store_as_subject(self):
        cases=[('same_building',STORE_ROW['name']+' is inside テスト施設.',{}),('area_anchor',STORE_ROW['name']+' is within テスト施設 district.',{'areaScope':'district'}),('relative_offset',STORE_ROW['name']+' is east of テスト施設 by a straight distance of 100m.',{'distanceMeters':100,'bearingDegrees':90})]
        for method,excerpt,extra in cases:
            with self.subTest(method=method):self.assertEqual(len(estimate_coordinates(row({**BUILDING_HINT,'method':method,'relationExcerpt':excerpt,**extra}),[ANCHOR])),1)

    def test_building_is_grounded_and_stays_estimated(self):
        result=estimate_coordinates(row(copy.deepcopy(BUILDING_HINT)),[ANCHOR])
        self.assertEqual(result[0]['coordinates'],ANCHOR['coordinates']);self.assertEqual(result[0]['coordinateEvidence']['status'],'estimated')
        self.assertEqual(result[0]['coordinateEvidence']['verification'],'needs_confirmation');validate_coordinate_evidence(result[0])
    def test_relative_uses_explicit_straight_distance_and_eight_directions(self):
        hint={**BUILDING_HINT,'method':'relative_offset','relationExcerpt':STORE_ROW['name']+' はテスト施設から東へ直線100m。','distanceMeters':100,'bearingDegrees':90}
        result=estimate_coordinates(row(hint),[ANCHOR]);coords=result[0]['coordinates']
        self.assertGreater(coords[0],130.4);self.assertAlmostEqual(meters_between(coords,ANCHOR['coordinates']),100,delta=1)
        validate_coordinate_evidence(result[0]);result[0]['coordinates']=[131,34]
        with self.assertRaises(ValidationError):validate_coordinate_evidence(result[0])
        for angle in range(0,360,45):self.assertAlmostEqual(meters_between(destination([179.999,0],1000,angle),[179.999,0]),1000,delta=1)
        self.assertLess(destination([179.999,0],1000,90)[0],0)
    def test_unsupported_or_unverified_relationship_cannot_estimate(self):
        for excerpt in ('徒歩5分','駅近く', '別支店 はテスト施設内にあります。',''):
            hint={**BUILDING_HINT,'relationExcerpt':excerpt}
            self.assertEqual(estimate_coordinates(row(hint),[ANCHOR]),[])
        self.assertEqual(estimate_coordinates({**STORE_ROW,'hints':[BUILDING_HINT]},[ANCHOR]),[])
        self.assertEqual(estimate_coordinates(row(BUILDING_HINT),[{**ANCHOR,'name':'別施設'}]),[])
    def test_area_requires_explicit_small_area(self):
        hint={**BUILDING_HINT,'method':'area_anchor','areaScope':'neighborhood','relationExcerpt':STORE_ROW['name']+' はテスト施設地区内にあります。'}
        result=estimate_coordinates(row(hint),[ANCHOR]);self.assertEqual(result[0]['coordinateEvidence']['precision'],'area');validate_coordinate_evidence(result[0])
        self.assertEqual(estimate_coordinates(row({**hint,'areaScope':'city'}),[ANCHOR]),[])
    def test_walking_distance_does_not_become_straight_distance(self):
        hint={**BUILDING_HINT,'method':'relative_offset','relationExcerpt':STORE_ROW['name']+' はテスト施設から東へ徒歩100m。','distanceMeters':100,'bearingDegrees':90}
        self.assertEqual(estimate_coordinates(row(hint),[ANCHOR]),[])
    def test_negated_building_and_reverse_relative_relationship_are_rejected(self):
        for excerpt in (STORE_ROW['name']+' はテスト施設内ではありません。',STORE_ROW['name']+' はテスト施設内ではない。'):
            self.assertEqual(estimate_coordinates(row({**BUILDING_HINT,'relationExcerpt':excerpt}),[ANCHOR]),[])
        hint={**BUILDING_HINT,'method':'relative_offset','relationExcerpt':'テスト施設は '+STORE_ROW['name']+' から東へ直線100m。','distanceMeters':100,'bearingDegrees':90}
        self.assertEqual(estimate_coordinates(row(hint),[ANCHOR]),[])
