import hashlib, re
from datetime import date
from services.budget_validation import normalize_budget

def validate_snapshot(snapshot, receipts_dir):
 if snapshot.get('schemaVersion') != 1: raise ValueError('Unsupported snapshot')
 try: normalize_budget({'categories':snapshot['categories']})
 except Exception as e: raise ValueError('Invalid budget') from e
 tx=snapshot['transactions'];ids={t['id'] for t in tx}
 if len(ids)!=len(tx):raise ValueError('Duplicate transaction')
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
 for r in snapshot['receipts'].values():
  if not re.fullmatch(r'demo-data/receipts/[A-Za-z0-9_-]+\.(png|jpg|pdf|webp)',r['path']):raise ValueError('Unsafe receipt path')
  p=receipts_dir/r['path']
  if not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest()!=r['sha256']:raise ValueError('Missing or corrupt receipt')
  if r.get('transactionId') and r['transactionId'] not in ids:raise ValueError('Missing receipt transaction')
