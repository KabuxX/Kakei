import asyncio, copy, json, sys, unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from agent.map_links import parse_map_link
from agent.web_coordinates import verify_page, WebCoordinateVerifier
from agent.place_http import PlaceProviderError
from coordinate_fixtures import STORE_ROW, BUILDING_HINT
from web_place_fixtures import SOURCE, NAME, ADDRESS

def page(body,url=SOURCE['url']):
    return {'url':url,'final_url':url,'redirects':[],'content_type':'text/html','body':body.encode(),'retrieved_at':1.0}

def article(name=NAME,address=ADDRESS,extra='緯度33.590 経度130.400'):
    return f'<article><h2>{name}</h2><p>{address}</p><p>{extra}</p></article>'

class MapLinkTests(unittest.TestCase):
    def test_pin_and_viewport_are_distinct(self):
        fixtures=[('https://www.google.com/maps/@33.59,130.4,18z','map_viewport'),('https://www.google.com/maps/search/?api=1&query=33.59,130.4','map_pin_url'),('https://maps.apple.com/?ll=33.59,130.4','map_viewport'),('https://maps.apple.com/?ll=33.59,130.4&q=店舗','map_pin_url'),('https://www.openstreetmap.org/?mlat=33.59&mlon=130.4#map=18/0/0','map_pin_url'),('https://www.openstreetmap.org/#map=18/33.59/130.4','map_viewport'),('https://www.google.com/maps/place/店舗/data=!3d33.59!4d130.4','map_pin_url')]
        for url,kind in fixtures:
            with self.subTest(url=url):
                result=parse_map_link(url);self.assertEqual(result['kind'],kind);self.assertEqual(result['coordinates'],[130.4,33.59])
    def test_unknown_and_invalid_links_do_not_supply_coordinates(self):
        for url in ('https://evil.example/?mlat=33.59&mlon=130.4','https://www.google.com/maps/@130.4,33.59,18z','https://maps.apple.com/?ll=NaN,1','https://www.google.com/maps/place/店舗/data=!3d33.59!4d130.4!3d34!4d131','https://map.yahoo.co.jp/?lat=33.59&lon=130.4','https://maps.apple.com/?ll=33.59,130.4&ll=34,131'):
            with self.subTest(url=url):self.assertIsNone(parse_map_link(url))

class VerificationTests(unittest.TestCase):
    def test_explicit_text_coordinates_are_store_bound(self):
        out=verify_page(copy.deepcopy(STORE_ROW),page(article()),SOURCE)
        self.assertEqual(out['candidates'][0]['coordinates'],[130.4,33.59])
        self.assertEqual(out['candidates'][0]['coordinateEvidence']['method'],'page_text')
        for body in (article(name='ドトール 博多駅店'),article(address='福岡県福岡市中央区天神9丁目9-9'),article(extra='位置は33.590,130.400'),article(extra='緯度130.400 経度33.590')):
            with self.subTest(body=body):self.assertEqual(verify_page(STORE_ROW,page(body),SOURCE)['candidates'],[])

    def test_other_store_in_same_page_cannot_lend_its_coordinates(self):
        body=article(extra='座標は未確認')+article(name='同じ施設の別店舗')
        self.assertEqual(verify_page(STORE_ROW,page(body),SOURCE)['candidates'],[])
        body=article()+article(name='同じ施設の別店舗',extra='緯度34.000 経度131.000')
        out=verify_page(STORE_ROW,page(body),SOURCE)
        self.assertEqual([c['coordinates'] for c in out['candidates']],[[130.4,33.59]])

    def test_structured_geo_is_bound_to_named_business(self):
        businesses=[{'@type':'LocalBusiness','name':'他の店','address':ADDRESS,'geo':{'latitude':34,'longitude':131}},{'@type':'LocalBusiness','name':NAME,'address':ADDRESS,'geo':{'latitude':33.59,'longitude':130.4}}]
        body='<script type="application/ld+json">'+json.dumps(businesses,ensure_ascii=False)+'</script>'
        out=verify_page(STORE_ROW,page(body),SOURCE)
        self.assertEqual([c['coordinates'] for c in out['candidates']],[[130.4,33.59]])
        self.assertEqual(out['candidates'][0]['coordinateEvidence']['method'],'structured_geo')

    def test_links_require_store_context_and_viewport_is_not_published(self):
        pin='https://www.google.com/maps/search/?api=1&query=33.59,130.4'
        out=verify_page(STORE_ROW,page(article(extra=f'<a href="{pin}">店舗の地図</a>')),SOURCE)
        self.assertEqual(out['candidates'][0]['coordinateEvidence']['method'],'map_pin_url')
        self.assertEqual(verify_page(STORE_ROW,page(f'<a href="{pin}">地図</a>'),SOURCE)['candidates'],[])
        viewport='https://www.google.com/maps/@33.59,130.4,18z'
        self.assertEqual(verify_page(STORE_ROW,page(article(extra=f'<a href="{viewport}">地図</a>')),SOURCE)['candidates'],[])

    def test_model_coordinates_and_different_url_labels_are_not_authority(self):
        row={**STORE_ROW,'coordinates':[130.4,33.59]}
        self.assertEqual(verify_page(row,page(article(extra='座標なし')),SOURCE)['candidates'],[])
        link='https://maps.apple.com/?ll=33.59,130.4&q=別支店'
        self.assertEqual(verify_page(row,page(article(extra=f'<a href="{link}">地図</a>')),SOURCE)['candidates'],[])

    def test_raw_relationship_is_verified_before_estimation(self):
        row={**copy.deepcopy(STORE_ROW),'hints':[copy.deepcopy(BUILDING_HINT)]}
        out=verify_page(row,page(article(extra=BUILDING_HINT['relationExcerpt'])),SOURCE)
        self.assertEqual(out['verifiedHints'],[BUILDING_HINT]);self.assertTrue(out['identityVerified'])
        self.assertEqual(verify_page(row,page(article(extra='関係は不明')),SOURCE)['verifiedHints'],[])

    def test_anchor_rows_are_not_store_candidates(self):
        row={**STORE_ROW,'name':'テスト施設','branch':'','role':'anchor'}
        out=verify_page(row,page(article(name='テスト施設')),SOURCE)
        self.assertEqual(out['candidates'],[]);self.assertEqual(out['anchors'][0]['coordinates'],[130.4,33.59])

class DiscoveryTests(unittest.IsolatedAsyncioTestCase):
    async def test_short_map_link_keeps_verified_source_context(self):
        short='https://maps.app.goo.gl/real-link'
        class Pages:
            def __init__(self):self.calls=[]
            async def fetch(self,url,**kwargs):
                self.calls.append(url)
                if url==SOURCE['url']:return page(article(extra=f'<a href="{short}">店舗の地図</a>'))
                return {**page(''), 'url':url,'final_url':'https://www.google.com/maps/search/?api=1&query=33.59,130.4','redirects':['https://www.google.com/maps/search/?api=1&query=33.59,130.4']}
        pages=Pages();row=copy.deepcopy(STORE_ROW);row['urls'].append('https://invented.example/map')
        result=await WebCoordinateVerifier(pages,None).verify(row,timeout=5)
        self.assertEqual(result['candidates'][0]['coordinates'],[130.4,33.59])
        self.assertNotIn('https://invented.example/map',pages.calls)
        self.assertIn(short,pages.calls)

    async def test_failed_site_does_not_prevent_another_source(self):
        other={**SOURCE,'id':'s2','url':'https://blog.example/store'}
        class Pages:
            async def fetch(self,url,**kwargs):
                if url==SOURCE['url']:raise PlaceProviderError('network')
                return page(article(),url)
        result=await WebCoordinateVerifier(Pages(),None).verify({**STORE_ROW,'sources':[SOURCE,other]},timeout=5)
        self.assertEqual(result['candidates'][0]['coordinates'],[130.4,33.59])
