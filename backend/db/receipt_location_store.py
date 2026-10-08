"""Versioned receipt confirmations, with short search leases and daily expiry."""
import json
import uuid
from db.store import Store, TrajectoryConflict, TrajectoryNotFound
from services.receipt_location_contracts import (ReceiptLocationResolution, METHODS, REASONS, STATUSES, normalize_location_input, location_fingerprint)
from services.validation import ValidationError


def _resolution(row) -> ReceiptLocationResolution:
    return dict(id=row['id'], receiptId=row['receipt_id'], revision=row['revision'],
                input=json.loads(row['input_json']), inputFingerprint=row['input_fingerprint'],
                status=row['status'], placeIds=json.loads(row['place_ids_json']),
                selectedPlaceId=row['selected_place_id'], method=row['method'], reason=row['reason'],
                confirmedAt=row['confirmed_at'], expiresAt=row['expires_at'], sourceTransactionId=row['source_transaction_id'])


class ReceiptLocationStore:
    def __init__(self, db_path):
        self.store = Store(db_path)

    @staticmethod
    def _asset(c, thread_id, receipt_id):
        if not c.execute('SELECT 1 FROM receipt_assets WHERE id=? AND thread_id=?', (receipt_id, thread_id)).fetchone():
            raise TrajectoryNotFound('レシートが見つかりません。')

    @staticmethod
    def _row(c, thread_id, receipt_id, now):
        row = c.execute('SELECT * FROM receipt_location_resolutions WHERE thread_id=? AND receipt_id=?', (thread_id, receipt_id)).fetchone()
        if not row:
            return None
        if row['expires_at'] <= now:
            expired = dict(row)
            expired.update(status='unavailable', reason='expired', confirmed_at=None, selected_place_id=None, method=None, place_ids_json='[]')
            return expired
        if row['status'] == 'searching' and row['processing_until'] <= now:
            c.execute("UPDATE receipt_location_resolutions SET status='unavailable', reason='budget_exceeded', processing_until=NULL, revision=revision+1 WHERE id=?", (row['id'],))
            row = c.execute('SELECT * FROM receipt_location_resolutions WHERE id=?', (row['id'],)).fetchone()
        return row

    @classmethod
    def _expected(cls, c, thread_id, receipt_id, revision, now, resolution_id=None):
        row = cls._row(c, thread_id, receipt_id, now)
        if not row or type(revision) is not int or row['revision'] != revision or (resolution_id is not None and row['id'] != resolution_id):
            raise TrajectoryConflict('店舗確認が更新されています。')
        return row

    def get(self, thread_id, receipt_id, *, now):
        with self.store._connection() as c:
            c.execute('BEGIN IMMEDIATE')
            row = self._row(c, thread_id, receipt_id, now)
            return _resolution(row) if row else None

    def seed(self, thread_id, receipt_id, input, *, status, method, now):
        value = normalize_location_input(input)
        if status not in ('needs_input', 'resolved') or (status == 'resolved' and (method not in ('receipt_address', 'existing_address') or not value['merchant'] or not value['merchantAddress'])) or (status == 'needs_input' and method is not None):
            raise ValidationError('location', '初回店舗確認を確認してください。')
        with self.store._connection() as c:
            c.execute('BEGIN IMMEDIATE'); self._asset(c, thread_id, receipt_id)
            existing = c.execute('SELECT * FROM receipt_location_resolutions WHERE thread_id=? AND receipt_id=?', (thread_id, receipt_id)).fetchone()
            if existing:
                result = _resolution(existing)
                if existing['expires_at'] <= now:
                    result.update(status='unavailable', reason='expired', confirmedAt=None, selectedPlaceId=None, method=None, placeIds=[])
                return result
            identifier = str(uuid.uuid4())
            c.execute('''INSERT INTO receipt_location_resolutions
                (id,thread_id,receipt_id,revision,input_json,input_fingerprint,status,place_ids_json,method,confirmed_at,expires_at)
                VALUES (?,?,?,1,?,?,?,'[]',?,?,?)''', (identifier, thread_id, receipt_id, json.dumps(value, ensure_ascii=False), location_fingerprint(value), status, method, now if status == 'resolved' else None, now + 86400))
            return _resolution(c.execute('SELECT * FROM receipt_location_resolutions WHERE id=?', (identifier,)).fetchone())

    def _replace(self, c, row, value, *, status, method, now, source_transaction_id=None, processing_until=None):
        c.execute('''UPDATE receipt_location_resolutions SET revision=revision+1,input_json=?,input_fingerprint=?,
            status=?,place_ids_json='[]',selected_place_id=NULL,method=?,reason=NULL,confirmed_at=?,
            processing_until=?,source_transaction_id=?,expires_at=? WHERE id=?''',
            (json.dumps(value, ensure_ascii=False), location_fingerprint(value), status, method,
             now if status == 'resolved' else None, processing_until, source_transaction_id,
             now + 86400 if row['expires_at'] <= now else row['expires_at'], row['id']))
        return _resolution(c.execute('SELECT * FROM receipt_location_resolutions WHERE id=?', (row['id'],)).fetchone())

    def begin_search(self, thread_id, receipt_id, input, revision, *, now, processing_until, source_transaction_id=None):
        value = normalize_location_input(input)
        if not value['merchant'] or not now < processing_until <= now + 20:
            raise ValidationError('location', '店舗名と検索期限を確認してください。')
        with self.store._connection() as c:
            c.execute('BEGIN IMMEDIATE')
            row = self._expected(c, thread_id, receipt_id, revision, now)
            return self._replace(c, row, value, status='searching', method=None, now=now, source_transaction_id=source_transaction_id, processing_until=processing_until)

    def finish_search(self, thread_id, receipt_id, resolution_id, revision, result, *, now, turn_context=None):
        status = result.get('status'); method = result.get('method'); reason = result.get('reason')
        ids = result.get('placeIds', []); selected = result.get('selectedPlaceId')
        if status not in STATUSES - {'needs_input', 'searching'} or (method is not None and method not in METHODS) or (reason is not None and reason not in REASONS) or not isinstance(ids, list) or len(ids) > 10 or any(not isinstance(p, str) or not p.strip() for p in ids) or len(set(ids)) != len(ids):
            raise ValidationError('location', '検索結果を確認してください。')
        if (status == 'resolved' and (method != 'google_unique' or len(ids) != 1 or selected != ids[0])) or (status != 'resolved' and (selected is not None or method is not None)) or (status == 'needs_selection' and len(ids) < 2):
            raise ValidationError('location', '検索結果の状態を確認してください。')
        with self.store._connection() as c:
            c.execute('BEGIN IMMEDIATE')
            row = self._expected(c, thread_id, receipt_id, revision, now, resolution_id)
            if row['status'] != 'searching' or row['processing_until'] <= now or result.get('inputFingerprint', row['input_fingerprint']) != row['input_fingerprint'] or ('input' in result and location_fingerprint(result['input']) != row['input_fingerprint']):
                raise TrajectoryConflict('この検索処理は無効になりました。')
            if turn_context:
                turn = c.execute("SELECT 1 FROM agent_turns WHERE thread_id=? AND client_message_id=? AND token=? AND status='processing'", tuple(turn_context[k] for k in ('thread_id', 'client_message_id', 'run_token'))).fetchone()
                if thread_id != turn_context['thread_id'] or not turn:
                    raise TrajectoryConflict('この検索処理は無効になりました。')
            c.execute('''UPDATE receipt_location_resolutions SET revision=revision+1,status=?,place_ids_json=?,selected_place_id=?,method=?,reason=?,confirmed_at=?,processing_until=NULL
                WHERE id=? AND revision=? AND status='searching' AND input_fingerprint=? AND processing_until>?''',
                (status, json.dumps(ids), selected, method, reason, now if status == 'resolved' else None, row['id'], revision, row['input_fingerprint'], now))
            return _resolution(c.execute('SELECT * FROM receipt_location_resolutions WHERE id=?', (row['id'],)).fetchone())

    def set_selection(self, thread_id, receipt_id, resolution_id, revision, place_id, *, now):
        with self.store._connection() as c:
            c.execute('BEGIN IMMEDIATE')
            row = self._expected(c, thread_id, receipt_id, revision, now, resolution_id)
            if row['status'] != 'needs_selection' or place_id not in json.loads(row['place_ids_json']):
                raise TrajectoryConflict('現在の候補から選択してください。')
            c.execute("UPDATE receipt_location_resolutions SET revision=revision+1,status='resolved',selected_place_id=?,method='google_selected',reason=NULL,confirmed_at=? WHERE id=?", (place_id, now, row['id']))
            return _resolution(c.execute('SELECT * FROM receipt_location_resolutions WHERE id=?', (row['id'],)).fetchone())

    def set_address(self, thread_id, receipt_id, input, revision, *, method, source_transaction_id=None, now):
        value = normalize_location_input(input)
        if not value['merchant'] or not value['merchantAddress'] or method not in ('receipt_address', 'user_address', 'existing_address'):
            raise ValidationError('location', '店舗名と住所を入力してください。')
        with self.store._connection() as c:
            c.execute('BEGIN IMMEDIATE')
            row = self._expected(c, thread_id, receipt_id, revision, now)
            return self._replace(c, row, value, status='resolved', method=method, now=now, source_transaction_id=source_transaction_id)
