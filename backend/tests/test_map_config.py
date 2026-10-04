import os,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient
from api.app import create_app

class MapConfigTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        root=Path(self.temp.name)
        self.client=TestClient(create_app(root/'test.sqlite3',root),base_url='http://localhost:8765')
        self.addCleanup(self.client.close)

    def test_public_token_is_available_before_initialization_without_other_secrets(self):
        with patch.dict(os.environ,{'GOOGLE_MAPS_BROWSER_API_KEY':'public-test','GOOGLE_PLACES_API_KEY':'secret-places','OPENAI_API_KEY':'secret-openai','GOOGLE_MAPS_MAP_ID':'fixture-map'}):
            response=self.client.get('/api/map-config')
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.json(),{'googleMapsBrowserKey':'public-test','googleMapId':'fixture-map'})
        self.assertEqual(response.headers['cache-control'],'no-store')

    def test_missing_and_secret_tokens_are_not_exposed(self):
        for token in ('','server-secret'):
            with self.subTest(token=token),patch.dict(os.environ,{'GOOGLE_MAPS_BROWSER_API_KEY':token,'GOOGLE_PLACES_API_KEY':'server-secret','GOOGLE_MAPS_MAP_ID':''}):
                response=self.client.get('/api/map-config')
                self.assertEqual(response.status_code,200)
                self.assertEqual(response.json(),{'googleMapsBrowserKey':None,'googleMapId':'DEMO_MAP_ID'})

    def test_external_hosts_cannot_read_configuration(self):
        self.assertEqual(self.client.get('/api/map-config',headers={'Host':'example.com'}).status_code,403)
