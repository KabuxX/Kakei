"""Server-bound place selection, including incomplete but reviewable proposals."""
import copy,hashlib
from services.agent_changes import canonical,read_state,prepare_changes
from services.trajectory_validation import validate_timeline
from services.validation import ValidationError
from db.store import TrajectoryConflict

def source_version(connection):return hashlib.sha256(canonical(read_state(connection)).encode()).hexdigest()

def unresolved(metadata):return [g for g in metadata.get('placeCandidates',[]) if not g.get('selectedCandidateId')]

def preview(connection,commands,metadata):
    if not unresolved(metadata):return prepare_changes(connection,resolve_places(commands,metadata))
    state=read_state(connection)
    before=[];after=[]
    for command in commands:
        identity=command['identity']
        if command['kind'].startswith('trajectory.'):
            before.append(next((d for d in state['timeline']['days'] if d['date']==identity.get('date')),None))
            after.append({**({'date':identity['date']} if 'date' in identity else {}),**command['data']})
        else:
            before.append(state['transactions'].get(identity.get('id')));after.append(command['data'])
    return {'baselines':{},'before':before,'after':after}

def check_source(connection,metadata):
    if metadata.get('sourceVersion') and source_version(connection)!=metadata['sourceVersion']:
        raise TrajectoryConflict('元データが変わりました。最新の取引から変更案を作り直してください。')

def resolve_places(commands,metadata):
    # Keep placeholder identities in editable commands so a saved-place selection
    # can be changed without rewriting unrelated references to that saved place.
    aliases={g['placeId']:g['selectedPlaceId'] for g in metadata.get('placeCandidates',[]) if g.get('selectedPlaceId')}
    def resolve(value):
        if isinstance(value,list):return [resolve(v) for v in value]
        if isinstance(value,dict):
            return {k:aliases.get(v,v) if k=='placeId' else [aliases.get(p,p) for p in v] if k=='viaPlaceIds' else resolve(v) for k,v in value.items()}
        return value
    return resolve(commands)

def choose(connection,commands,metadata,candidate_id=None,manual=None,place_id=None,confirmed=False):
    check_source(connection,metadata)
    commands=copy.deepcopy(commands);metadata=copy.deepcopy(metadata)
    groups=metadata.get('placeCandidates',[])
    if manual is not None:
        group=next((g for g in groups if g['placeId']==place_id),None)
        if not group or not isinstance(manual,dict) or set(manual)!={'name','coordinates'}:
            raise ValidationError('place','確認した店舗名と座標を指定してください。')
        place={'name':manual['name'],'coordinates':manual['coordinates'],'address':None,'sourceUrl':None,'placeEvidence':'user','attribution':None}
        candidate_id='manual'
    else:
        group=next((g for g in groups if any(c['id']==candidate_id for c in g['candidates'])),None)
        if not group:raise ValidationError('candidateId','この変更案の候補を選んでください。')
        candidate=next(c for c in group['candidates'] if c['id']==candidate_id)
        requires_confirmation=('coordinateEvidence' in candidate and candidate['coordinateEvidence'].get('verification')!='user_confirmed') or candidate.get('geocoding',{}).get('verification')=='needs_confirmation'
        if requires_confirmation and confirmed is not True:raise ValidationError('confirmed','住所と地図を確認してから、この地点を選んでください。')
        if candidate.get('savedPlaceId'):
            identifier=candidate['savedPlaceId']
            if identifier not in read_state(connection)['timeline']['places']:
                raise TrajectoryConflict('選択した地点が変更されました。')
            group['selectedPlaceId']=identifier;place=None
        else:
            place={k:candidate[k] for k in ('name','address','coordinates','sourceUrl','attribution')};place['placeEvidence']='provider'
            place.update({k:candidate[k] for k in ('sources','geocoding','coordinateEvidence') if k in candidate})
            if requires_confirmation:
                key='coordinateEvidence' if 'coordinateEvidence' in place else 'geocoding'
                place[key]={**place[key],'verification':'user_confirmed'}
    # Remove this group's previously staged place only; preserve edits to the
    # day and all other selections. Rebase new:<index> links after removal.
    retained=[(i,c) for i,c in enumerate(commands) if not (c['kind'].startswith('trajectory.') and c['identity'].get('kind')=='place' and c['identity'].get('id')==group['placeId'])]
    from services.agent_changes import resolve_ids
    mapping={f'new:{old}':f'new:{new}' for new,(old,c) in enumerate(retained) if c['kind']=='transaction.create'}
    commands=resolve_ids([c for _,c in retained],mapping)
    metadata.setdefault('authorizedPlaces',{}).pop(group['placeId'],None)
    if place:
        group.pop('selectedPlaceId',None)
        validate_timeline({'places':{group['placeId']:place},'days':[]})
        commands.append({'kind':'trajectory.create','identity':{'kind':'place','id':group['placeId']},'data':place})
        metadata.setdefault('authorizedPlaces',{})[group['placeId']]=place
    group['selectedCandidateId']=candidate_id
    return commands,metadata

def validate_bound_places(commands,metadata):
    allowed=metadata.get('authorizedPlaces',{})
    for command in commands:
        if command['kind'].startswith('trajectory.') and command['identity'].get('kind')=='place':
            if allowed.get(command['identity'].get('id'))!=command['data']:
                raise ValidationError('place','地点は候補選択または座標入力で指定してください。')

def review_labels(connection, commands, after):
    state=read_state(connection);labels={}
    for value in after:
        if not isinstance(value,dict):continue
        for event in value.get('events',[]):
            place=state['timeline']['places'].get(event.get('placeId'))
            if place:labels[event['placeId']]=place['name']
            identifier=event.get('transactionId');record=state['transactions'].get(identifier)
            if record:labels[identifier]=f"{record['title']} · {record['amount']}円"
        for leg in value.get('legs',[]):
            identifier=leg.get('transportTransactionId');record=state['transactions'].get(identifier)
            if record:labels[identifier]=f"{record['title']} · {record['amount']}円"
    return labels
