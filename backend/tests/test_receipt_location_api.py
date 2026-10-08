import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient
from api.app import create_app
from services.receipt_location import ReceiptLocationService
from test_receipt_location_service import Client

class ApiTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
        self.provider=Client()
        app=create_app(Path(tmp.name)/'db',Path(tmp.name),receipt_location_service_factory=lambda store:ReceiptLocationService(store,client_factory=lambda:self.provider,wall_clock=lambda:100,monotonic=lambda:10))
        with app.state.store._connection() as c:
            c.execute("INSERT INTO meta VALUES ('initialized','true')")
            c.execute("INSERT INTO agent_threads VALUES ('t',0,'test')")
            c.execute("INSERT INTO receipt_assets VALUES ('r','t','image/png','hash',1,X'00',0,999999,NULL)")
        self.client=TestClient(app,base_url='http://localhost:8765');self.addCleanup(self.client.close)
        self.base='/api/agent/threads/t/receipts/r/location'
    def post(self,path,value):
        return self.client.post(self.base+path,json=value,headers={'origin':'http://localhost:8765'})
    def test_scoped_get_search_and_selection(self):
        self.assertIsNone(self.client.get(self.base).json()['locationResolution'])
        result=self.post('/search',{'input':{'merchant':'店'},'revision':0})
        self.assertEqual(result.status_code,200);r=result.json()['locationResolution']
        forged_selection=self.post('/selection',{'resolutionId':r['id'],'revision':r['revision'],'placeId':'fake'})
        self.assertEqual(forged_selection.status_code,400)
        selected=self.post('/selection',{'resolutionId':r['id'],'revision':r['revision'],'placeId':'p'})
        self.assertEqual(selected.status_code,200)
        stale_selection=self.post('/selection',{'resolutionId':r['id'],'revision':r['revision'],'placeId':'p'})
        self.assertEqual(stale_selection.status_code,409)
        self.assertEqual(self.client.get(self.base.replace('/t/','/other/')).status_code,404)
    def test_address_validation_and_current_get(self):
        self.assertEqual(self.post('/address',{'input':{'merchant':'店'},'revision':0}).status_code,400)
        result=self.post('/address',{'input':{'merchant':'店','merchantAddress':'本人住所'},'revision':0})
        self.assertEqual(result.status_code,200)
        self.assertEqual(self.client.get(self.base).json(),result.json())
        self.assertEqual(self.post('/search',{'input':{'merchant':'店'},'revision':False}).status_code,409)
