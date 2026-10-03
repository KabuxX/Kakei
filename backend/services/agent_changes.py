"""Pure proposal preview and atomic approval on the caller's SQLite connection."""
import copy
import hashlib
import json
import time
import uuid
from agent.contracts import command_dicts
from db.store import Store, TrajectoryConflict, TrajectoryNotFound, _apply_trajectory_command
from db.trajectory_store import read_trajectory_timeline, replace_trajectory
from services.trajectory_mutation import parse_trajectory_command
from services.trajectory_validation import validate_timeline
from services.validation import ValidationError, normalize_transaction


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def read_state(connection):
    items = {}
    for row in connection.execute('SELECT * FROM transaction_items ORDER BY transaction_id, position'):
        items.setdefault(row['transaction_id'], []).append({'name': row['name'], 'amount': row['amount']})
    records = {row['id']: Store._record(row, items.get(row['id'], []))
               for row in connection.execute('SELECT * FROM transactions')}
    return {'transactions': records, 'timeline': read_trajectory_timeline(connection)}


def baseline_value(state, key):
    kind, identifier = key.split(':', 1)
    if kind == 'transaction':
        return state['transactions'].get(identifier)
    if kind == 'day':
        return next((day for day in state['timeline']['days'] if day['date'] == identifier), None)
    if kind == 'place':
        return state['timeline']['places'].get(identifier)
    if kind == 'transactions-day':
        return sorted((r for r in state['transactions'].values() if r['date'][:10] == identifier), key=lambda r: r['id'])
    raise ValidationError('proposal', '元データの参照が正しくありません。')


def fingerprints(state, keys):
    return {key: hashlib.sha256(canonical(baseline_value(state, key)).encode()).hexdigest() for key in keys}


def prepare_changes(connection, commands):
    commands = command_dicts(commands)
    original = read_state(connection)
    state = copy.deepcopy(original)
    before, after, keys = [None] * len(commands), [None] * len(commands), set()
    changed_days, changed_transactions = set(), set()
    trajectory_days = {c['identity'].get('date') for c in commands if c['kind'].startswith('trajectory.')}
    indexed = sorted(enumerate(commands), key=lambda pair: pair[1]['identity'].get('kind') != 'place')
    for index, command in indexed:
        domain, action = command['kind'].split('.')
        identity, draft = command['identity'], copy.deepcopy(command['data'])
        if domain == 'transaction':
            expected = set() if action == 'create' else {'id'}
            if set(identity) != expected:
                raise ValidationError('identity', '取引の対象IDが正しくありません。')
            identifier = f'new:{index}' if action == 'create' else identity['id']
            old = state['transactions'].get(identifier)
            if action == 'update' and old is None:
                raise TrajectoryNotFound('取引が見つかりません。')
            receipt_ids = draft.pop('receiptIds', [])
            if not isinstance(receipt_ids, list) or len(receipt_ids) > 8 or any(not isinstance(i, str) for i in receipt_ids):
                raise ValidationError('receiptIds', 'レシートの指定を確認してください。')
            confirm = draft.pop('confirmTime', False)
            if type(confirm) is not bool:
                raise ValidationError('confirmTime', '時刻の確認を選択してください。')
            record = {'id': identifier, **normalize_transaction(draft)}
            if old and old['date'] == record['date'] and not confirm:
                record['timeEstimated'] = old['timeEstimated']
            before[index] = copy.deepcopy(old)
            if receipt_ids:
                record['receiptIds'] = receipt_ids
            after[index] = record
            state['transactions'][identifier] = record
            changed_transactions.add(identifier)
            if old:
                keys.add('transaction:' + identifier)
                for day in original['timeline']['days']:
                    visits = [e for e in day['events'] if e.get('transactionId') == identifier]
                    fares = [leg for leg in day['legs'] if leg.get('transportTransactionId') == identifier]
                    if visits or fares:
                        changed_days.add(day['date'])
                        if visits and old.get('merchant') != record.get('merchant') and day['date'] not in trajectory_days:
                            raise TrajectoryConflict('店舗を変更するには、参照する軌跡も修正してください。')
        else:
            parsed = parse_trajectory_command({**identity, 'data': draft}, 'POST' if action == 'create' else 'PUT')
            if parsed.kind == 'place':
                key = 'place:' + parsed.id
                for day in state['timeline']['days']:
                    if any(e['placeId'] == parsed.id for e in day['events']):
                        changed_days.add(day['date'])
            else:
                key = 'day:' + parsed.date
                changed_days.add(parsed.date)
            keys.add(key)
            before[index] = copy.deepcopy(baseline_value(state, key))
            _apply_trajectory_command(state['timeline'], parsed, action)
            after[index] = copy.deepcopy(baseline_value(state, key))
    try:
        validate_timeline(state['timeline'], require_complete=False)
    except ValueError as error:
        raise ValidationError('trajectory', str(error)) from error
    for date in changed_days:
        keys.update(('day:' + date, 'transactions-day:' + date))
        day = baseline_value(state, 'day:' + date)
        if day is None:
            continue
        old_day = baseline_value(original, 'day:' + date) or {'events': [], 'legs': []}
        used = set()
        for event in day['events']:
            old_event = next((e for e in old_day['events'] if e['id'] == event['id']), None)
            if event.get('timeEvidence', 'legacy') == 'legacy' and event != old_event:
                raise ValidationError('timeEvidence', '新規・変更した訪問には時刻の根拠を指定してください。')
            keys.add('place:' + event['placeId'])
            identifier = event.get('transactionId')
            if not identifier:
                continue
            if identifier in used:
                raise ValidationError('trajectory', '同じ取引を複数の訪問へ割り当てることはできません。')
            used.add(identifier)
            record = _check_transaction_reference(state, identifier, date)
            if event.get('timeEvidence') == 'exact' and record.get('timeEstimated'):
                raise ValidationError('timeEvidence', '仮設定の取引時刻は確定時刻として扱えません。')
            if not identifier.startswith('new:'):
                keys.add('transaction:' + identifier)
        for leg in day['legs']:
            if leg.get('modeEvidence', 'legacy') == 'legacy' and leg not in old_day['legs']:
                raise ValidationError('modeEvidence', '新規・変更した区間には移動手段の根拠を指定してください。')
            keys.update('place:' + p for p in leg.get('viaPlaceIds', []))
            identifier = leg.get('transportTransactionId')
            if identifier:
                record = _check_transaction_reference(state, identifier, date)
                if record['type'] != 'expense' or record['category'] != '交通':
                    raise ValidationError('trajectory', '交通費の取引を指定してください。')
                if not identifier.startswith('new:'):
                    keys.add('transaction:' + identifier)
    return {'baselines': fingerprints(original, keys), 'before': before, 'after': after,
            'state': state, 'changedTransactions': changed_transactions,
            'changedDays': changed_days, 'commands': commands}


def _check_transaction_reference(state, identifier, date):
    record = state['transactions'].get(identifier)
    if record is None or record['date'][:10] != date:
        raise TrajectoryConflict('軌跡には同じ日の取引を指定してください。関連する取引と軌跡をまとめて修正できます。')
    return record


def validate_agent_commands(connection, commands):
    return prepare_changes(connection, commands)['baselines']


def resolve_ids(value, mapping):
    if isinstance(value, list):
        return [resolve_ids(item, mapping) for item in value]
    if isinstance(value, dict):
        return {key: mapping.get(item, item) if key in ('id', 'transactionId', 'transportTransactionId') and isinstance(item, str)
                else resolve_ids(item, mapping) for key, item in value.items()}
    return value


def apply_proposal(connection, proposal_id, revision):
    row = connection.execute('SELECT * FROM agent_proposals WHERE id = ?', (proposal_id,)).fetchone()
    if row is None:
        raise TrajectoryNotFound('変更案が見つかりません。')
    if type(revision) is not int or revision != row['revision']:
        raise TrajectoryConflict('変更案が更新されています。最新の差分を確認してください。')
    if row['status'] == 'applied':
        return json.loads(row['result_json'])
    if row['status'] != 'pending' or row['expires_at'] <= time.time():
        raise TrajectoryConflict('この変更案は期限切れか却下済みです。新しい案を作成してください。')
    from services.agent_places import unresolved, validate_bound_places
    metadata = json.loads(row['metadata_json'])
    if metadata.get('orderRequired') and not metadata.get('orderConfirmed'):
        raise TrajectoryConflict('時刻が不明・推定の訪問順序を確認してください。')
    if unresolved(metadata):
        raise TrajectoryConflict('未確定の地点があります。候補または座標を選んでください。')
    validate_bound_places(json.loads(row['commands_json']), metadata)
    expected = json.loads(row['baselines_json'])
    if fingerprints(read_state(connection), expected) != expected:
        raise TrajectoryConflict('元データが変更されました。差分を更新して再確認してください。')
    preview = prepare_changes(connection, json.loads(row['commands_json']))
    mapping = {f'new:{index}': str(uuid.uuid5(uuid.UUID(proposal_id), f'transaction:{index}'))
               for index, command in enumerate(preview['commands']) if command['kind'] == 'transaction.create'}
    changed = []
    for index, command in enumerate(preview['commands']):
        if command['kind'].startswith('transaction.'):
            record = resolve_ids(preview['after'][index], mapping)
            if command['kind'] == 'transaction.create':
                Store._insert(connection, record)
            else:
                Store._update(connection, record)
            from db.receipt_store import ReceiptStore
            ReceiptStore.attach(connection, command['data'].get('receiptIds', []), record['id'], row['thread_id'])
            changed.append(record)
    if any(c['kind'].startswith('trajectory.') for c in preview['commands']):
        replace_trajectory(connection, resolve_ids(preview['state']['timeline'], mapping))
        connection.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('trajectory_modified', '1')")
    result = {'proposalId': proposal_id, 'revision': revision, 'transactions': changed,
              'trajectoryDates': sorted(preview['changedDays'])}
    connection.execute("""UPDATE agent_proposals SET status = 'applied', result_json = ?,
        before_json = ?, after_json = ?, applied_at = ? WHERE id = ?""",
        (canonical(result), canonical(preview['before']), canonical(resolve_ids(preview['after'], mapping)), time.time(), proposal_id))
    return result
