"""Synthetic coordinate evidence; not facts about a real store."""
import copy
from web_place_fixtures import SOURCE, NAME, ADDRESS

OBSERVATION = {'sourceId':'s1','kind':'structured_geo','excerpt':'latitude=33.59 longitude=130.4','coordinates':[130.4,33.59]}
PUBLISHED_PLACE = {'name':NAME,'address':ADDRESS,'coordinates':[130.4,33.59],'sourceUrl':SOURCE['url'],'attribution':'店舗情報','placeEvidence':'provider','sources':[copy.deepcopy(SOURCE)],
    'coordinateEvidence':{'version':1,'status':'published','method':'structured_geo','sourceIds':['s1'],'retrievedAt':1.0,'precision':'point','note':'店舗ページに掲載された位置。現地の精度は未確認。','verification':'needs_confirmation','observations':[copy.deepcopy(OBSERVATION)]}}
BUILDING_HINT = {'method':'same_building','anchorName':'テスト施設','anchorAddress':ADDRESS,'relationSourceIds':['s1'],'relationExcerpt':NAME+' はテスト施設内にあります。','distanceMeters':None,'bearingDegrees':None,'areaScope':None}
ANCHOR = {'name':'テスト施設','address':ADDRESS,'coordinates':[130.4,33.59],'sources':[copy.deepcopy(SOURCE)],'observations':[copy.deepcopy(OBSERVATION)]}
ESTIMATED_PLACE = copy.deepcopy(PUBLISHED_PLACE)
ESTIMATED_PLACE['coordinateEvidence'].update(status='estimated',method='same_building',precision='building',note='建物・施設内の推定位置。誤差範囲は未確認。',basis={'anchorName':'テスト施設','anchorAddress':ADDRESS,'anchorCoordinates':[130.4,33.59],'relationSourceIds':['s1']})
ESTIMATED_PLACE['coordinateEvidence']['observations'].append({'sourceId':'s1','kind':'relationship','excerpt':BUILDING_HINT['relationExcerpt'],'coordinates':None})
STORE_ROW = {'id':'store-row','name':NAME,'branch':'西鉄福岡駅店','address':ADDRESS,'country_code':'jp','locality':'福岡市','sources':[copy.deepcopy(SOURCE)],'evidenceText':NAME+' | '+ADDRESS,'unresolved':[], 'role':'store','urls':[SOURCE['url']],'hints':[]}
