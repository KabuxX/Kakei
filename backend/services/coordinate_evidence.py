"""Structural validation and atomic source rebinding for coordinate evidence."""
import copy
import math
from services.place_evidence import text, timestamp, validate_sources
from services.validation import ValidationError

PUBLISHED_METHODS = {'page_text','structured_geo','map_pin_url'}
ESTIMATED_METHODS = {'same_building':'building','relative_offset':'nearby','area_anchor':'area'}

def invalid():
    raise ValidationError('coordinateEvidence','座標の根拠・推定方法・出典を確認してください。')

def valid_coordinates(value):
    return isinstance(value,list) and len(value)==2 and all(type(x) in (int,float) and math.isfinite(x) for x in value) and -180<=value[0]<=180 and -90<=value[1]<=90

def references(value, available):
    if not isinstance(value,list) or not 1<=len(value)<=6 or any(not isinstance(x,str) or x not in available for x in value) or len(set(value))!=len(value):invalid()
    return set(value)

def validate_coordinate_evidence(place: dict) -> None:
    evidence=place.get('coordinateEvidence')
    fields={'version','status','method','sourceIds','retrievedAt','precision','note','verification','observations'}
    if not isinstance(evidence,dict) or not fields<=evidence.keys() or evidence.keys()-fields-{'basis'} or 'geocoding' in place:invalid()
    if type(evidence['version'])!=int or evidence['version']!=1 or evidence['verification'] not in ('needs_confirmation','user_confirmed'):invalid()
    validate_sources(place.get('sources'),maximum=6)
    refs=references(evidence['sourceIds'],{s['id'] for s in place['sources']})
    timestamp(evidence['retrievedAt']);text(evidence['note'],500,'note')
    if not valid_coordinates(place.get('coordinates')):invalid()
    observations=evidence['observations']
    if not isinstance(observations,list) or not 1<=len(observations)<=4:invalid()
    for observation in observations:
        if not isinstance(observation,dict) or set(observation)!={'sourceId','kind','excerpt','coordinates'}:invalid()
        if not isinstance(observation['sourceId'],str) or observation['sourceId'] not in refs or observation['kind'] not in PUBLISHED_METHODS|{'map_viewport','relationship'}:invalid()
        text(observation['excerpt'],2048,'excerpt')
        if observation['kind']=='relationship':
            if observation['coordinates'] is not None:invalid()
        elif not valid_coordinates(observation['coordinates']):invalid()
    status,method=evidence['status'],evidence['method']
    if not isinstance(method,str):invalid()
    if status=='published':
        if method not in PUBLISHED_METHODS or evidence['precision']!='point' or 'basis' in evidence:invalid()
        if not any(o['kind']==method and o['coordinates']==place['coordinates'] for o in observations):invalid()
    elif status=='estimated':
        if method not in ESTIMATED_METHODS or evidence['precision']!=ESTIMATED_METHODS[method]:invalid()
        basis=evidence.get('basis');required={'anchorName','anchorAddress','anchorCoordinates','relationSourceIds'}
        if method=='relative_offset':required|={'distanceMeters','bearingDegrees'}
        if not isinstance(basis,dict) or set(basis)!=required:invalid()
        text(basis['anchorName'],200,'anchorName');text(basis['anchorAddress'],500,'anchorAddress')
        relations=references(basis['relationSourceIds'],refs)
        if not valid_coordinates(basis['anchorCoordinates']):invalid()
        if not relations<={o['sourceId'] for o in observations if o['kind']=='relationship'}:invalid()
        if not any(o['coordinates']==basis['anchorCoordinates'] and (o['kind'] in PUBLISHED_METHODS or method=='area_anchor' and o['kind']=='map_viewport') for o in observations):invalid()
        if method=='relative_offset':
            if type(basis['distanceMeters'])!=int or not 1<=basis['distanceMeters']<=5000 or type(basis['bearingDegrees'])!=int or basis['bearingDegrees'] not in range(0,360,45):invalid()
        elif place['coordinates']!=basis['anchorCoordinates']:invalid()
    else:invalid()

def rebind_candidate_sources(candidate: dict, mapping: dict[str,str]) -> dict:
    result=copy.deepcopy(candidate)
    for source in result.get('sources',[]):source['id']=mapping.get(source['id'],source['id'])
    evidence=result.get('coordinateEvidence')
    if evidence:
        evidence['sourceIds']=[mapping.get(i,i) for i in evidence['sourceIds']]
        for observation in evidence['observations']:observation['sourceId']=mapping.get(observation['sourceId'],observation['sourceId'])
        if 'basis' in evidence:evidence['basis']['relationSourceIds']=[mapping.get(i,i) for i in evidence['basis']['relationSourceIds']]
    return result
