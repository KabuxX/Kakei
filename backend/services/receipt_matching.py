"""Deterministic receipt duplicate evidence; never automatically selects an edit."""
from datetime import date
import unicodedata
from services.agent_changes import read_state

def merchant_key(value):return ''.join(unicodedata.normalize('NFKC',value or '').casefold().split())

def find_receipt_matches(connection,candidate,sha256):
    records=read_state(connection)['transactions']
    exact={row[0] for row in connection.execute('SELECT transaction_id FROM receipt_assets WHERE sha256=? AND transaction_id IS NOT NULL',(sha256,))}
    matches=[]
    try:requested=date.fromisoformat(candidate.date or '')
    except ValueError:requested=None
    merchant=merchant_key(candidate.merchant)
    for record in records.values():
        reason='hash' if record['id'] in exact else None
        if not reason and requested and merchant and record['amount']==candidate.total:
            other=merchant_key(record.get('merchant'))
            if other and (merchant in other or other in merchant) and abs((date.fromisoformat(record['date'][:10])-requested).days)<=3:reason='near'
        if reason:matches.append({'transaction':record,'reason':reason})
    return sorted(matches,key=lambda m:(m['reason']!='hash',m['transaction']['date']))[:20]
