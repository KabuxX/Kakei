"""Estimate only from fetched relationships and verified geographic anchors."""
import copy,re,uuid
from agent.place_matching import compact
from services.merchant_address import addresses_match
from services.coordinate_math import destination
from services.coordinate_evidence import validate_coordinate_evidence,valid_coordinates
from services.validation import ValidationError
DIRECTIONS={0:'北',45:'北東',90:'東',135:'南東',180:'南',225:'南西',270:'西',315:'北西'}
ENGLISH_DIRECTIONS={0:'north',45:'northeast',90:'east',135:'southeast',180:'south',225:'southwest',270:'west',315:'northwest'}

def relation_valid(row,hint):
    excerpt=compact(hint.get('relationExcerpt',''));method=hint.get('method')
    if not excerpt or compact(row['name']) not in excerpt or compact(hint['anchorName']) not in excerpt:return False
    # A presence of "inside" or a direction alone does not establish a relation.
    if re.search(r'(では(?:あり)?ません|ではない|でない|ありません|ない|なく|not|outside|no longer)',excerpt):return False
    target,anchor=map(re.escape,(compact(row['name']),compact(hint['anchorName'])))
    subject=target+r'(?:は|が|の店舗は)?'+anchor
    if method=='same_building':return bool(re.search(subject+r'(?:の)?(?:建物|施設)?内',excerpt) or re.search(target+r'と'+anchor+r'(?:は)?(?:同じ建物|同一施設)',excerpt) or re.search(target+r'is(?:inside|within)'+anchor,excerpt))
    if method=='area_anchor':return hint.get('areaScope') in ('block','neighborhood','district') and bool(re.search(subject+r'(?:の)?(?:地区内|街区内|区域内|町内)',excerpt) or re.search(target+r'iswithin'+anchor+r'(?:district|neighborhood|block)',excerpt))
    if method!='relative_offset':return False
    d,b=hint.get('distanceMeters'),hint.get('bearingDegrees')
    if type(d)!=int or not 1<=d<=5000 or type(b)!=int or b not in DIRECTIONS:return False
    if re.search(r'(徒歩|経路|道のり|約\d+分|walking|route)',excerpt):return False
    relation=re.search(subject+r'から(北東|南東|南西|北西|北|東|南|西)(?:へ|に|方向|方)(?:約)?直線(?:約)?'+str(d)+r'(?:m|メートル)(?!\d)',excerpt)
    english=re.search(target+r'is'+ENGLISH_DIRECTIONS[b]+r'of'+anchor+r'by(?:a)?straightdistanceof'+str(d)+r'(?:m|meters)(?!\d)',excerpt)
    return bool(relation and relation[1]==DIRECTIONS[b] or english)

def estimate_coordinates(row,anchors):
    candidates=[]
    for hint in sorted(row.get('verifiedHints',[]),key=lambda h:['same_building','relative_offset','area_anchor'].index(h['method']) if h['method'] in ('same_building','relative_offset','area_anchor') else 9):
        if not relation_valid(row,hint):continue
        for anchor in anchors:
            if compact(hint['anchorName'])!=compact(anchor['name']) or not addresses_match(hint['anchorAddress'],anchor['address']) or not valid_coordinates(anchor['coordinates']):continue
            sources={s['id']:copy.deepcopy(s) for s in row['sources']+anchor['sources']}
            if not all(i in sources for i in hint['relationSourceIds']):continue
            method=hint['method'];obs=[copy.deepcopy(o) for o in anchor['observations'] if o['coordinates']==anchor['coordinates'] and (o['kind'] in ('page_text','structured_geo','map_pin_url') or method=='area_anchor' and o['kind']=='map_viewport')][:1]
            if not obs:continue
            obs.extend({'sourceId':i,'kind':'relationship','excerpt':hint['relationExcerpt'],'coordinates':None} for i in hint['relationSourceIds'])
            if len(obs)>4:continue
            ids=list(dict.fromkeys(o['sourceId'] for o in obs));basis={'anchorName':anchor['name'],'anchorAddress':anchor['address'],'anchorCoordinates':anchor['coordinates'],'relationSourceIds':hint['relationSourceIds']}
            coords=anchor['coordinates'];precision={'same_building':'building','relative_offset':'nearby','area_anchor':'area'}[method]
            if method=='relative_offset':
                basis.update(distanceMeters=hint['distanceMeters'],bearingDegrees=hint['bearingDegrees']);coords=destination(coords,hint['distanceMeters'],hint['bearingDegrees'])
            note={'same_building':'同一の建物・施設を基準にした推定位置。','relative_offset':'掲載された直線距離と方角を基準にした推定位置。','area_anchor':'店舗を含む地区を基準にした推定位置。'}[method]+'入口・誤差範囲は未確認。'
            candidate={'id':str(uuid.uuid4()),'name':row['name'],'address':row['address'],'coordinates':coords,'sourceUrl':sources[ids[0]]['url'],'attribution':'Web出典を基準とした推定','sources':[sources[i] for i in ids],'matchReasons':['grounded_estimate'],'coordinateEvidence':{'version':1,'status':'estimated','method':method,'sourceIds':ids,'retrievedAt':max(sources[i]['retrievedAt'] for i in ids),'precision':precision,'note':note,'verification':'needs_confirmation','observations':obs,'basis':basis}}
            try:validate_coordinate_evidence(candidate)
            except ValidationError:continue
            candidates.append(candidate)
            if len(candidates)>=3:return candidates
    return candidates
