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
    def test_geolonia_requires_detailed_address_and_point(self):
        from geolonia_fixtures import GEOLONIA_PLACE
        validate_place_evidence(copy.deepcopy(GEOLONIA_PLACE))
        for patch in ({'level':3},{'pointLevel':3},{'level':True},{'record':None}):
            place=copy.deepcopy(GEOLONIA_PLACE);place['coordinateEvidence']['addressMatch'].update(patch)
            with self.subTest(patch=patch),self.assertRaises(ValidationError):validate_place_evidence(place)

    def test_geolonia_coordinates_and_record_are_bound(self):
        from geolonia_fixtures import GEOLONIA_PLACE
        mutations=[lambda p:p.update(coordinates=[139.8,35.7]),
            lambda p:p['coordinateEvidence']['addressMatch']['record']['fields'].update(rsdt_num='4'),
            lambda p:p['coordinateEvidence']['addressMatch']['fetches'][0].update(sha256='invalid'),
            lambda p:p['coordinateEvidence']['addressMatch']['fetches'][0].update(range={'offset':-1,'length':100}),
            lambda p:p['coordinateEvidence']['addressMatch']['fetches'][0].update(url='https://evil.example/data'),
            lambda p:p['coordinateEvidence']['addressMatch'].update(matchedAddress='東京都文京区本郷一丁目2-4'),
            lambda p:p['coordinateEvidence']['addressMatch'].update(originalAddress='東京都文京区本郷1-2-4'),
            lambda p:p['coordinateEvidence'].update(version=True)]
        for mutation in mutations:
            p=copy.deepcopy(GEOLONIA_PLACE);mutation(p)
            with self.subTest(mutation=mutation),self.assertRaises(ValidationError):validate_place_evidence(p)

    def test_geolonia_numeric_dataset_version_is_safe(self):
        from geolonia_fixtures import GEOLONIA_PLACE
        place=copy.deepcopy(GEOLONIA_PLACE)
        url=place['sources'][0]['url']+'?v=1234'
        place['sources'][0]['url']=url;place['coordinateEvidence']['addressMatch']['fetches'][0]['url']=url
        validate_place_evidence(place)
        place['sources'][0]['url']=url+'&token=secret'
        place['coordinateEvidence']['addressMatch']['fetches'][0]['url']=place['sources'][0]['url']
        with self.assertRaises(ValidationError):validate_place_evidence(place)

    def test_geolonia_rebind_and_bounding_keep_atomic_evidence(self):
        from geolonia_fixtures import GEOLONIA_PLACE
        from services.coordinate_evidence import rebind_candidate_sources
        from db.agent_search_store import bounded_result
        original=copy.deepcopy(GEOLONIA_PLACE);rebound=rebind_candidate_sources(original,{'g1':'new'})
        self.assertEqual(rebound['coordinateEvidence']['addressMatch']['fetches'][0]['sourceId'],'new')
        validate_place_evidence(rebound);self.assertEqual(original,GEOLONIA_PLACE)
        large=copy.deepcopy(GEOLONIA_PLACE);large['coordinateEvidence']['note']='x'*9000
        result=bounded_result({'status':'found','candidates':[large,GEOLONIA_PLACE],'sources':GEOLONIA_PLACE['sources']})
        self.assertEqual(result['candidates'],[GEOLONIA_PLACE]);self.assertEqual(result['omittedCandidates'],1)

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
