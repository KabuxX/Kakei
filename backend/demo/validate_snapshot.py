import hashlib, re
from datetime import date
from services.budget_validation import normalize_budget

def unique_ids(records, path, label, key='id', seen=None):
 if seen is None:seen=set()
 for index,record in enumerate(records):
  identifier=record.get(key)
  if not isinstance(identifier,str) or not identifier or identifier in seen:raise ValueError(f'Duplicate or missing {label}: {path}[{index}].{key}')
  seen.add(identifier)
 return seen

def receipt_references(value, path, receipts):
 # Original links must resolve even in retained history. Transaction IDs in
 # historical before/after/results need not still exist in current records.
 if isinstance(value,list):
  for index,item in enumerate(value):receipt_references(item,f'{path}[{index}]',receipts)
 elif isinstance(value,dict):
  for key,item in value.items():
   location=f'{path}.{key}'
   if key=='receiptId':
    if not isinstance(item,str) or item not in receipts:raise ValueError(f'Missing original reference: {location}')
   elif key=='receiptIds':
    if not isinstance(item,list):raise ValueError(f'Invalid original references: {location}')
    for index,identifier in enumerate(item):
     if not isinstance(identifier,str) or identifier not in receipts:raise ValueError(f'Missing original reference: {location}[{index}]')
   else:receipt_references(item,location,receipts)

def validate_snapshot(snapshot, receipts_dir):
 if snapshot.get('schemaVersion') != 1: raise ValueError('Unsupported snapshot')
 try: normalize_budget({'categories':snapshot['categories']})
 except Exception as e: raise ValueError('Invalid budget') from e
 tx=snapshot['transactions'];ids=unique_ids(tx,'transactions','transaction')
 threads=unique_ids(snapshot['threads'],'threads','thread');proposals=set();messages=set()
 for index,thread in enumerate(snapshot['threads']):
  path=f'threads[{index}]'
  unique_ids(thread.get('messages',[]),f'{path}.messages','message',seen=messages)
  unique_ids(thread.get('proposals',[]),f'{path}.proposals','proposal',seen=proposals)
  unique_ids(thread.get('receiptReviews',[]),f'{path}.receiptReviews','receipt review',key='receiptId')
  for index,proposal in enumerate(thread.get('proposals',[])):
   if proposal.get('threadId')!=thread['id']:raise ValueError(f'Invalid containing thread: {path}.proposals[{index}].threadId')
 for t in tx:date.fromisoformat(t['date'][:10])
 timeline=snapshot['timeline'];seen=set();dates=set()
 for d in timeline['days']:
  date.fromisoformat(d['date'])
  if d['date'] in dates:raise ValueError('Duplicate day')
  dates.add(d['date']);local=set()
  for e in d['events']:
   if not e.get('id') or e['id'] in seen:raise ValueError('Duplicate or missing event')
   seen.add(e['id']);local.add(e['id'])
   if e['placeId'] not in timeline['places'] or e.get('transactionId') and e['transactionId'] not in ids:raise ValueError('Missing event reference')
  for l in d['legs']:
   if l['fromEventId'] not in local or l['toEventId'] not in local or any(p not in timeline['places'] for p in l.get('viaPlaceIds',[])) or l.get('transportTransactionId') and l['transportTransactionId'] not in ids:raise ValueError('Missing leg reference')
 for identifier,r in snapshot['receipts'].items():
  if identifier!=r.get('id'):raise ValueError(f'Invalid receipt table key: receipts.{identifier}.id')
  if r.get('threadId') not in threads:raise ValueError(f'Missing receipt thread: receipts.{identifier}.threadId')
  if not re.fullmatch(r'demo-data/receipts/[A-Za-z0-9_-]+\.(png|jpg|pdf|webp)',r['path']):raise ValueError('Unsafe receipt path')
  p=receipts_dir/r['path']
  if not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest()!=r['sha256']:raise ValueError('Missing or corrupt receipt')
  if r.get('transactionId') and r['transactionId'] not in ids:raise ValueError('Missing receipt transaction')
 receipt_references(tx,'transactions',snapshot['receipts'])
 receipt_references(snapshot['threads'],'threads',snapshot['receipts'])
