"""Read a consistent SQLite backup, exposing only public display records."""
import hashlib,json,re,sqlite3,tempfile,shutil
from contextlib import closing
from pathlib import Path
from db.store import Store
from db.trajectory_store import read_trajectory_timeline
from db.agent_store import proposal_record
from services.transaction_addresses import read_transaction_addresses,annotate_location_status
from demo.validate_snapshot import validate_snapshot
from services.receipt_images import primary_jpeg

# Business display DTOs may be nested. Never include execution/cache metadata.
PRIVATE={'baselines','sourceVersion','authorizedPlaces','placeCandidates','searchIds','token','input','raw','rawResponse','google_place_coordinates','geocoding','coordinateEvidence'}
def clean(value):
 if isinstance(value,list):return [clean(v) for v in value]
 if not isinstance(value,dict):return value
 if value.get('provider')=='google':
  return {k:clean(v) for k,v in value.items() if k not in PRIVATE|{'coordinates','provider','providerPlaceId','attribution'}}
 return {k:clean(v) for k,v in value.items() if k not in PRIVATE}

def export_demo(db_path:Path,out_dir:Path,curated_path:Path,captured_at:str)->dict:
 curated=json.loads(curated_path.read_text());out_dir=Path(out_dir)
 with tempfile.TemporaryDirectory() as tmp:
  root=Path(tmp);db=root/'snapshot.sqlite3'
  with closing(sqlite3.connect(Path(db_path).resolve().as_uri()+'?mode=ro',uri=True)) as original,closing(sqlite3.connect(db)) as backup:original.backup(backup)
  with closing(sqlite3.connect(db)) as c:
   c.row_factory=sqlite3.Row
   transactions=[]
   for r in c.execute('SELECT * FROM transactions ORDER BY date DESC,id DESC'):
    items=[{'name':i['name'],'amount':i['amount']} for i in c.execute('SELECT * FROM transaction_items WHERE transaction_id=? ORDER BY position',(r['id'],))]
    transactions.append(Store._record(r,items))
   timeline=annotate_location_status(c,read_trajectory_timeline(c));addresses=read_transaction_addresses(c);lookup={}
   for p in timeline['places'].values():
    if p.get('provider')=='google':
     gid=p['providerPlaceId'];v=curated.get(gid,{})
     p.update({k:v[k] for k in ('name','address','sourceUrl','attribution') if k in v})
     p['coordinates']=v.get('coordinates');p['demoPositionUnconfirmed']=p['coordinates'] is None;p['demoNote']=v.get('note','独立した座標の根拠を確認できないため位置未確認。')
     p.pop('provider');p.pop('providerPlaceId');lookup[gid]=clean(p)
   timeline=clean(timeline)
   threads=[]
   for t in c.execute('SELECT * FROM agent_threads ORDER BY created_at DESC'):
    messages=[]
    for m in c.execute('SELECT * FROM agent_messages WHERE thread_id=? ORDER BY created_at,rowid',(t['id'],)):
     meta=json.loads(m['metadata_json']);messages.append({'id':m['id'],'clientMessageId':m['client_message_id'],'role':m['role'],'text':m['text'],'createdAt':m['created_at'],'sources':clean(meta.get('sources',[])),**{k:clean(meta[k]) for k in ('trajectoryCreation','placeSearch') if k in meta}})
    proposals=[]
    for p in c.execute('SELECT * FROM agent_proposals WHERE thread_id=? ORDER BY created_at',(t['id'],)):
     dto=proposal_record(p);dto['metadata']={k:clean(v) for k,v in dto['metadata'].items() if k in ('receiptId','receiptReview','targetChoice','referenceLabels','orderRequired')};proposals.append(clean(dto))
    reviews={}
    for r in c.execute("SELECT result_json FROM agent_turns WHERE thread_id=? AND status='complete' ORDER BY started_at",(t['id'],)):
     review=json.loads(r[0]).get('receiptReview')
     if review:reviews[review['receiptId']]=clean(review)
    threads.append({'id':t['id'],'title':t['title'],'createdAt':t['created_at'],'messages':messages,'proposals':proposals,'receiptReviews':list(reviews.values())})
   receipts={};public=root/'public';(public/'demo-data/receipts').mkdir(parents=True)
   ext={'image/png':'png','image/jpeg':'jpg','image/webp':'webp','image/heic':'heic','application/pdf':'pdf'}
   for r in c.execute('SELECT * FROM receipt_assets'):
    if not re.fullmatch('[A-Za-z0-9_-]+',r['id']):raise ValueError('Unsafe receipt ID')
    path=f"demo-data/receipts/{r['id']}.{ext[r['mime_type']]}";(public/path).write_bytes(r['data'])
    receipts[r['id']]={'id':r['id'],'mimeType':r['mime_type'],'pageCount':r['page_count'],'sha256':r['sha256'],'createdAt':r['created_at'],'transactionId':r['transaction_id'],'threadId':r['thread_id'],'path':path}
    if r['mime_type']=='image/heic':
     preview_path=f"demo-data/receipts/{r['id']}-preview.jpg";preview_data=primary_jpeg(r['data'])
     (public/preview_path).write_bytes(preview_data)
     receipts[r['id']].update(previewPath=preview_path,previewSha256=hashlib.sha256(preview_data).hexdigest())
   s={'schemaVersion':1,'exportedAt':captured_at,'transactions':transactions,'categories':{r['category']:r['amount'] for r in c.execute('select * from category_budgets')},'timeline':timeline,'addresses':addresses,'threads':threads,'receipts':receipts,'placeLookup':lookup}
   validate_snapshot(s,public)
   data=json.dumps(s,ensure_ascii=False,allow_nan=False,indent=2)+'\n'
   manifest={'schemaVersion':1,'exportedAt':captured_at,'latestMonth':max((t['date'][:7] for t in transactions),default=captured_at[:7]),'counts':{'transactions':len(transactions),'days':len(timeline['days']),'events':sum(len(d['events']) for d in timeline['days']),'places':len(timeline['places']),'threads':len(threads),'messages':sum(len(t['messages']) for t in threads),'receipts':len(receipts),'categories':len(s['categories'])},'snapshotSha256':hashlib.sha256(data.encode()).hexdigest(),'receiptHashes':{k:r['sha256'] for k,r in receipts.items()},'unconfirmedPlaces':[k for k,p in timeline['places'].items() if p.get('demoPositionUnconfirmed')]}
   (out_dir/'data').mkdir(parents=True,exist_ok=True);(out_dir/'data/snapshot.json').write_text(data);(out_dir/'data/manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n');shutil.copytree(public,out_dir/'public',dirs_exist_ok=True)
   return manifest
