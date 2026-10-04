"""Synthetic address records; never claims about a real store."""
import copy
import json

URL = 'https://japanese-addresses-v2.geoloniamaps.com/api/ja/test.txt'
FETCH = {'sourceId':'g1','url':URL,'retrievedAt':1.0,'range':{'offset':0,'length':100},'sha256':'a'*64,'updatedAt':None}
COMPONENTS = {'pref':'東京都','city':'文京区','town':'本郷一丁目','addr':'2-3'}
RECORD = {'kind':'rsdt','fields':{'blk_num':'2','rsdt_num':'3','point':[139.7,35.7]}}
ADDRESS = '東京都文京区本郷1-2-3'
OBSERVATION = {'sourceId':'g1','kind':'geolonia_address','excerpt':json.dumps({'components':COMPONENTS,'record':RECORD},ensure_ascii=False),'coordinates':[139.7,35.7]}
DETAILED_RESULT = {'match':{**COMPONENTS,'other':'','level':8,'point':{'lng':139.7,'lat':35.7,'level':8},'record':RECORD},'proof':{'fetches':[FETCH],'observation':OBSERVATION}}
COARSE_RESULT = copy.deepcopy(DETAILED_RESULT)
COARSE_RESULT['match']['point']['level']=3
COARSE_RESULT['match']['record']=None
GEOLONIA_PLACE = {'name':'合成テスト店舗','address':ADDRESS,'coordinates':[139.7,35.7],'sourceUrl':URL,'attribution':'Geolonia japanese-addresses-v2 · CC BY 4.0（加工して利用）','placeEvidence':'provider','sources':[{'id':'g1','title':'Geolonia japanese-addresses-v2','url':URL,'kind':'directory','retrievedAt':1.0}],
    'coordinateEvidence':{'version':2,'status':'address_matched','method':'geolonia_address','sourceIds':['g1'],'retrievedAt':1.0,'precision':'address','note':'住所に対応する座標。店舗の入口は未確認。','verification':'needs_confirmation','observations':[OBSERVATION],
        'addressMatch':{'provider':'geolonia','libraryVersion':'3.1.3','originalAddress':ADDRESS,'queryAddress':ADDRESS,'matchedAddress':'東京都文京区本郷一丁目2-3','strategies':['original'],'level':8,'pointLevel':8,'components':COMPONENTS,'record':RECORD,'fetches':[FETCH]}}}
