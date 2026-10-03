"""Read-only address context derived from saved transaction/place associations."""
import copy
from services.merchant_address import location_status


def read_transaction_addresses(connection, transaction_id: str | None = None) -> list[dict]:
    from db.store import TrajectoryNotFound
    result = {}
    if transaction_id is not None:
        if not connection.execute('SELECT 1 FROM transactions WHERE id=?',(transaction_id,)).fetchone():
            raise TrajectoryNotFound('取引が見つかりません。')
        result[transaction_id] = {'transactionId': transaction_id, 'places': []}
    rows = connection.execute('''SELECT DISTINCT t.id AS transaction_id,t.merchant_address,
        p.id,p.name,p.address,p.longitude,p.latitude
        FROM transactions t JOIN trajectory_events e ON e.transaction_id=t.id
        JOIN trajectory_places p ON e.place_id=p.id
        WHERE t.type='expense' AND (? IS NULL OR t.id=?) ORDER BY t.id,p.id''', (transaction_id, transaction_id))
    for row in rows:
        entry=result.setdefault(row['transaction_id'],{'transactionId':row['transaction_id'],'places':[]})
        entry['places'].append({'placeId':row['id'],'name':row['name'],'address':row['address'],
            'coordinates':[row['longitude'],row['latitude']],
            'status':location_status(row['merchant_address'],row['address'])})
    return list(result.values())


def annotate_location_status(connection, timeline: dict | None) -> dict | None:
    if timeline is None:
        return None
    result=copy.deepcopy(timeline)
    contexts=read_transaction_addresses(connection)
    statuses={(c['transactionId'],p['placeId']):p['status'] for c in contexts for p in c['places']}
    for day in result['days']:
        for event in day['events']:
            event['locationStatus']=statuses.get((event.get('transactionId'),event['placeId']),'trajectory_only')
    return result
