"""Bounded date-specific facts for trajectory proposals."""
import json
from services.trajectory_mutation import _date
from services.validation import ValidationError
from db.store import Store
from db.trajectory_store import read_trajectory_day
from services.transaction_addresses import annotate_location_status

def build_trajectory_context(connection, day):
    day=_date(day)
    records=[]
    rows=connection.execute('SELECT * FROM transactions WHERE substr(date,1,10)=? ORDER BY date,id LIMIT 101',(day,)).fetchall()
    if len(rows)>100:raise ValidationError('date','この日の取引は100件を超えています。対象を絞ってください。')
    for row in rows:
        items=[{'name':i['name'],'amount':i['amount']} for i in connection.execute('SELECT name,amount FROM transaction_items WHERE transaction_id=? ORDER BY position',(row['id'],))]
        records.append(Store._record(row,items))
    value={'date':day,'transactions':records,'savedDay':annotate_location_status(connection,read_trajectory_day(connection,day))}
    if len(json.dumps(value,ensure_ascii=False).encode())>65536:raise ValidationError('date','この日のデータが大きすぎます。対象を絞ってください。')
    return value

def order_required(after):
    return any(isinstance(value,dict) and sum(e.get('timeEvidence') in ('estimated','unknown') for e in value.get('events',[]))>1 for value in after)
