import copy, json, sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from db.store import Store
from db.schema import ensure_schema
from db.trajectory_store import read_trajectory_timeline
from services.place_evidence import validate_place_evidence
from services.validation import ValidationError
from coordinate_fixtures import PUBLISHED_PLACE, ESTIMATED_PLACE
from web_place_fixtures import PLACE

class CoordinateEvidenceTests(unittest.TestCase):
    def test_normal_evidence_forms(self):
        area=copy.deepcopy(ESTIMATED_PLACE);area['coordinateEvidence'].update(method='area_anchor',precision='area')
        relative=copy.deepcopy(ESTIMATED_PLACE);relative['coordinateEvidence'].update(method='relative_offset',precision='nearby')
        relative['coordinateEvidence']['basis'].update(distanceMeters=100,bearingDegrees=90)
        relative['coordinates']=[130.401079,33.59]
        for place in (PUBLISHED_PLACE,ESTIMATED_PLACE,area,relative):
            with self.subTest(method=place['coordinateEvidence']['method']):validate_place_evidence(place)

    def test_missing_and_invalid_evidence_is_rejected(self):
        patches=[{'sourceIds':['missing']},{'sourceIds':[]},{'sourceIds':['s1','s1']},{'version':True},{'status':'exact'}, {'method':'same_building'},{'precision':'area'},{'retrievedAt':float('nan')},{'note':'長'*501},{'secret':'key'}, {'verification':'verified'}]
        for patch in patches:
            place=copy.deepcopy(PUBLISHED_PLACE);place['coordinateEvidence'].update(patch)
            with self.subTest(patch=patch),self.assertRaises(ValidationError):validate_place_evidence(place)
        for patch in ({'observations':[]},{'observations':[{'sourceId':'s1','kind':'unknown','excerpt':'x','coordinates':[1,2]}]}):
            place=copy.deepcopy(PUBLISHED_PLACE);place['coordinateEvidence'].update(patch)
            with self.subTest(patch=patch),self.assertRaises(ValidationError):validate_place_evidence(place)

    def test_estimate_basis_and_observations_are_bound(self):
        for basis in ({'anchorCoordinates':[0,0]},{'relationSourceIds':['missing']},{'distanceMeters':100}):
            place=copy.deepcopy(ESTIMATED_PLACE);place['coordinateEvidence']['basis'].update(basis)
            with self.subTest(basis=basis),self.assertRaises(ValidationError):validate_place_evidence(place)
        place=copy.deepcopy(ESTIMATED_PLACE);place['coordinateEvidence'].pop('basis')
        with self.assertRaises(ValidationError):validate_place_evidence(place)
        for value in (0,5001,True):
            place=copy.deepcopy(ESTIMATED_PLACE);place['coordinateEvidence'].update(method='relative_offset',precision='nearby')
            place['coordinateEvidence']['basis'].update(distanceMeters=value,bearingDegrees=90)
            with self.subTest(value=value),self.assertRaises(ValidationError):validate_place_evidence(place)
        place=copy.deepcopy(ESTIMATED_PLACE);place['coordinateEvidence'].update(method='relative_offset',precision='nearby')
        place['coordinateEvidence']['basis'].update(distanceMeters=100,bearingDegrees=46)
        with self.assertRaises(ValidationError):validate_place_evidence(place)

    def test_published_coordinates_must_match_observation(self):
        for coords in ([0,0],[float('inf'),0],[130.4,91],[True,33.59]):
            place=copy.deepcopy(PUBLISHED_PLACE);place['coordinates']=coords
            with self.subTest(coords=coords),self.assertRaises(ValidationError):validate_place_evidence(place)

    def test_new_and_legacy_provider_cannot_be_mixed(self):
        place={**copy.deepcopy(PUBLISHED_PLACE),'geocoding':copy.deepcopy(PLACE['geocoding'])}
        with self.assertRaises(ValidationError):validate_place_evidence(place)

    def test_storage_update_export_and_old_schema(self):
        with tempfile.TemporaryDirectory() as directory:
            store=Store(Path(directory)/'test.sqlite');store.initialize([])
            day={'date':'2026-10-04','events':[{'id':'visit','time':'09:00','placeId':'shop'}],'legs':[]}
            for original in (PUBLISHED_PLACE,ESTIMATED_PLACE,PLACE):
                store.sync_trajectory({'places':{'shop':copy.deepcopy(original)},'days':[day]})
                reopened=Store(store.db_path)
                saved=reopened.get_trajectory_day(day['date'])['places']['shop']
                self.assertEqual(saved,original)
                with reopened._connection() as c:
                    self.assertEqual(json.loads(json.dumps(read_trajectory_timeline(c)))['places']['shop'],original)
            with store._connection() as c:
                c.execute('ALTER TABLE trajectory_places DROP COLUMN coordinate_evidence_json')
                c.commit();ensure_schema(c);c.commit();ensure_schema(c);c.commit()
                self.assertIsNone(c.execute('SELECT coordinate_evidence_json FROM trajectory_places').fetchone()[0])
            self.assertEqual(Store(store.db_path).get_trajectory_day(day['date'])['places']['shop'],PLACE)

    def test_source_rebinding_changes_all_references_without_mutation(self):
        from services.coordinate_evidence import rebind_candidate_sources
        original=copy.deepcopy(ESTIMATED_PLACE)
        rebound=rebind_candidate_sources(original,{'s1':'new-id'})
        self.assertEqual(rebound['sources'][0]['id'],'new-id')
        self.assertEqual(rebound['coordinateEvidence']['sourceIds'],['new-id'])
        self.assertEqual(rebound['coordinateEvidence']['basis']['relationSourceIds'],['new-id'])
        self.assertEqual([o['sourceId'] for o in rebound['coordinateEvidence']['observations']],['new-id','new-id'])
        self.assertEqual(original,ESTIMATED_PLACE)
