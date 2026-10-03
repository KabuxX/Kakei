"""Synthetic evidence; these addresses/coordinates do not verify a real shop."""
SOURCE={'id':'s1','title':'店舗情報','url':'https://store.example/detail?id=12','kind':'unknown','retrievedAt':1.0}
NAME='ドトールコーヒーショップ 西鉄福岡駅店'
ADDRESS='福岡県福岡市中央区天神1丁目2-3'
GEOCODING={'provider':'mapbox','providerId':'mapbox.1','queryAddress':ADDRESS,'matchedAddress':ADDRESS,'featureType':'address','accuracy':'rooftop','matchCode':{'confidence':'exact','address_number':'matched'},'permanent':True,'retrievedAt':1.0}
PLACE={'name':NAME,'address':ADDRESS,'coordinates':[130.4,33.59],'sourceUrl':SOURCE['url'],'attribution':'© Mapbox','placeEvidence':'provider','sources':[SOURCE],'geocoding':GEOCODING}
WEB_PLACE={'id':'w1','name':NAME,'branch':'西鉄福岡駅店','address':ADDRESS,'country_code':'jp','locality':'福岡市','sources':[SOURCE],'evidenceText':NAME+' '+ADDRESS,'unresolved':[]}
