"""Durable conversation and review proposal repository."""
import json
import time
import uuid
from pathlib import Path
from agent.contracts import command_dicts
from db.store import Store, TrajectoryConflict, TrajectoryNotFound
from services.validation import ValidationError


def dumps(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':'))


def proposal_record(row):
    return {'id': row['id'], 'threadId': row['thread_id'], 'revision': row['revision'],
            'status': row['status'], 'commands': json.loads(row['commands_json']),
            'createdAt': row['created_at'], 'expiresAt': row['expires_at'],
            'result': json.loads(row['result_json']) if row['result_json'] else None,
            'before': json.loads(row['before_json']), 'after': json.loads(row['after_json']),
            'metadata': json.loads(row['metadata_json'])}


class AgentStore:
    def __init__(self, db_path: Path):
        self.store = Store(db_path)
        self.db_path = self.store.db_path

    @staticmethod
    def _thread(connection, thread_id):
        row = connection.execute('SELECT * FROM agent_threads WHERE id = ?', (thread_id,)).fetchone()
        if row is None:
            raise TrajectoryNotFound('会話が見つかりません。')
        return row

    @staticmethod
    def _expire(connection):
        from db.receipt_store import cleanup
        cleanup(connection)
        connection.execute("UPDATE agent_proposals SET status = 'expired' WHERE status = 'pending' AND expires_at <= ?", (time.time(),))

    @staticmethod
    def _pending(connection, proposal_id, revision=None):
        row = connection.execute('SELECT * FROM agent_proposals WHERE id = ?', (proposal_id,)).fetchone()
        if row is None:
            raise TrajectoryNotFound('変更案が見つかりません。')
        if row['status'] != 'pending' or row['expires_at'] <= time.time():
            raise TrajectoryConflict('この変更案は保存できません。新しい案を作成してください。')
        if revision is not None and (type(revision) is not int or revision != row['revision']):
            raise TrajectoryConflict('変更案が更新されています。最新の差分を確認してください。')
        return row

    def create_thread(self):
        thread = {'id': str(uuid.uuid4()), 'createdAt': time.time(), 'title': '新しい会話'}
        with self.store._connection() as c:
            c.execute('INSERT INTO agent_threads(id, created_at, title) VALUES (?, ?, ?)',
                      (thread['id'], thread['createdAt'], thread['title']))
        return thread

    def list_threads(self):
        with self.store._connection() as c:
            return [{'id': row['id'], 'title': row['title'], 'createdAt': row['created_at']}
                    for row in c.execute('SELECT * FROM agent_threads ORDER BY created_at DESC LIMIT 100')]

    def get_thread(self, thread_id):
        with self.store._connection() as c:
            self._expire(c)
            row = c.execute('SELECT * FROM agent_threads WHERE id = ?', (thread_id,)).fetchone()
            if row is None:
                return None
            messages = [{'id': m['id'], 'clientMessageId': m['client_message_id'], 'role': m['role'],
                         'text': m['text'], 'createdAt': m['created_at']} for m in c.execute(
                             'SELECT * FROM agent_messages WHERE thread_id = ? ORDER BY created_at, rowid', (thread_id,))]
            proposals = [proposal_record(p) for p in c.execute(
                'SELECT * FROM agent_proposals WHERE thread_id = ? ORDER BY created_at', (thread_id,))]
            return {'id': row['id'], 'title': row['title'], 'createdAt': row['created_at'], 'messages': messages, 'proposals': proposals}

    def append_message(self, thread_id, client_message_id, role, text):
        if (not isinstance(client_message_id, str) or not 1 <= len(client_message_id) <= 200
                or role not in ('user', 'assistant') or not isinstance(text, str) or not 1 <= len(text) <= 16000):
            raise ValidationError('message', 'メッセージの形式を確認してください。')
        with self.store._connection() as c:
            c.execute('BEGIN IMMEDIATE')
            self._thread(c, thread_id)
            old = c.execute('SELECT * FROM agent_messages WHERE thread_id = ? AND client_message_id = ?', (thread_id, client_message_id)).fetchone()
            if old:
                if old['text'] != text or old['role'] != role:
                    raise TrajectoryConflict('同じ送信IDで別のメッセージは送信できません。')
                return {'id': old['id'], 'role': role, 'text': text, 'createdAt': old['created_at']}
            now, identifier = time.time(), str(uuid.uuid4())
            c.execute('INSERT INTO agent_messages VALUES (?, ?, ?, ?, ?, ?)', (identifier, thread_id, client_message_id, role, text, now))
            if role == 'user':
                c.execute("UPDATE agent_threads SET title = ? WHERE id = ? AND title = '新しい会話'", (text[:40], thread_id))
            return {'id': identifier, 'role': role, 'text': text, 'createdAt': now}

    def create_proposal(self, thread_id, commands, baselines=None):
        with self.store._connection() as c:
            c.execute('BEGIN IMMEDIATE')
            return self._create_proposal(c, thread_id, commands)

    def _create_proposal(self, c, thread_id, commands):
        from services.agent_changes import prepare_changes
        commands = command_dicts(commands)
        identifier, now = str(uuid.uuid4()), time.time()
        self._thread(c, thread_id)
        self._expire(c)
        preview = prepare_changes(c, commands)
        c.execute("""INSERT INTO agent_proposals
            (id, thread_id, revision, status, commands_json, baselines_json, created_at, expires_at, before_json, after_json)
            VALUES (?, ?, 1, 'pending', ?, ?, ?, ?, ?, ?)""",
            (identifier, thread_id, dumps(commands), dumps(preview['baselines']), now, now + 86400,
             dumps(preview['before']), dumps(preview['after'])))
        return proposal_record(c.execute('SELECT * FROM agent_proposals WHERE id = ?', (identifier,)).fetchone())

    def begin_turn(self, thread_id, client_id, text, receipt_id=None):
        if (not isinstance(client_id, str) or not 1 <= len(client_id) <= 200
                or not isinstance(text, str) or not text.strip() or len(text) > 16000
                or (receipt_id is not None and not isinstance(receipt_id, str))):
            raise ValidationError('message', 'メッセージの形式を確認してください。')
        encoded = dumps({'text': text, 'receiptId': receipt_id})
        with self.store._connection() as c:
            c.execute('BEGIN IMMEDIATE')
            self._thread(c, thread_id)
            old = c.execute('SELECT * FROM agent_turns WHERE thread_id=? AND client_message_id=?', (thread_id, client_id)).fetchone()
            if old:
                if old['input_json'] != encoded:
                    raise TrajectoryConflict('同じ送信IDで内容を変更できません。')
                if old['status'] == 'complete':
                    return {'cached': json.loads(old['result_json'])}
            if c.execute("SELECT 1 FROM agent_turns WHERE thread_id=? AND status='processing' AND started_at>?", (thread_id, time.time()-70)).fetchone():
                raise TrajectoryConflict('応答を作成中です。少し待って再送してください。')
            token = str(uuid.uuid4())
            c.execute("INSERT OR REPLACE INTO agent_turns VALUES (?, ?, ?, ?, 'processing', ?, NULL)", (thread_id, client_id, encoded, token, time.time()))
            c.execute('INSERT OR IGNORE INTO agent_messages VALUES (?, ?, ?, ?, ?, ?)', (str(uuid.uuid4()), thread_id, 'user:'+client_id, 'user', text, time.time()))
            c.execute("UPDATE agent_threads SET title=? WHERE id=? AND title='新しい会話'", (text[:40], thread_id))
            from services.agent_changes import canonical, read_state
            import hashlib
            version = hashlib.sha256(canonical(read_state(c)).encode()).hexdigest()
            return {'token': token, 'sourceVersion': version}

    def fail_turn(self, thread_id, client_id, token):
        with self.store._connection() as c:
            c.execute("UPDATE agent_turns SET status='failed' WHERE thread_id=? AND client_message_id=? AND token=? AND status='processing'", (thread_id, client_id, token))

    def complete_turn(self, thread_id, client_id, lease, result):
        from services.agent_changes import canonical, read_state
        import hashlib
        text = result.get('text')
        if not isinstance(text, str) or not 1 <= len(text) <= 16000:
            raise ValidationError('message', '応答の形式が正しくありません。')
        with self.store._connection() as c:
            c.execute('BEGIN IMMEDIATE')
            row = c.execute('SELECT * FROM agent_turns WHERE thread_id=? AND client_message_id=?', (thread_id, client_id)).fetchone()
            if not row or row['token'] != lease['token'] or row['status'] != 'processing':
                raise TrajectoryConflict('この応答は無効になりました。再送してください。')
            proposal = None
            if result.get('commands'):
                if hashlib.sha256(canonical(read_state(c)).encode()).hexdigest() != lease['sourceVersion']:
                    raise TrajectoryConflict('応答中に元データが変更されました。再送してください。')
                proposal = self._create_proposal(c, thread_id, result['commands'])
            message = {'id': str(uuid.uuid4()), 'role': 'assistant', 'text': text, 'createdAt': time.time()}
            c.execute('INSERT INTO agent_messages VALUES (?, ?, ?, ?, ?, ?)', (message['id'], thread_id, 'assistant:'+client_id, 'assistant', text, message['createdAt']))
            response = {'message': message, 'proposal': proposal}
            c.execute("UPDATE agent_turns SET status='complete', result_json=? WHERE thread_id=? AND client_message_id=?", (dumps(response), thread_id, client_id))
            return response

    def get_proposal(self, proposal_id):
        with self.store._connection() as c:
            self._expire(c)
            row = c.execute('SELECT * FROM agent_proposals WHERE id = ?', (proposal_id,)).fetchone()
            if row is None:
                raise TrajectoryNotFound('変更案が見つかりません。')
            return proposal_record(row)

    def revise_proposal(self, proposal_id, expected_revision, commands):
        from services.agent_changes import prepare_changes
        commands = command_dicts(commands)
        if type(expected_revision) is not int:
            raise ValidationError('revision', '確認した版を指定してください。')
        with self.store._connection() as c:
            c.execute('BEGIN IMMEDIATE')
            self._expire(c)
            self._pending(c, proposal_id, expected_revision)
            preview = prepare_changes(c, commands)
            c.execute('''UPDATE agent_proposals SET commands_json = ?, revision = revision + 1,
                baselines_json = ?, before_json = ?, after_json = ? WHERE id = ?''',
                (dumps(commands), dumps(preview['baselines']), dumps(preview['before']), dumps(preview['after']), proposal_id))
            return proposal_record(c.execute('SELECT * FROM agent_proposals WHERE id = ?', (proposal_id,)).fetchone())

    def reject_proposal(self, proposal_id, revision=None):
        with self.store._connection() as c:
            c.execute('BEGIN IMMEDIATE')
            self._expire(c)
            row = c.execute('SELECT * FROM agent_proposals WHERE id = ?', (proposal_id,)).fetchone()
            if row is None:
                raise TrajectoryNotFound('変更案が見つかりません。')
            if row['status'] != 'rejected':
                self._pending(c, proposal_id, revision)
                c.execute("UPDATE agent_proposals SET status = 'rejected' WHERE id = ?", (proposal_id,))
            return proposal_record(c.execute('SELECT * FROM agent_proposals WHERE id = ?', (proposal_id,)).fetchone())

    def delete_thread(self, thread_id):
        with self.store._connection() as c:
            c.execute('BEGIN IMMEDIATE')
            self._thread(c, thread_id)
            c.execute("DELETE FROM agent_proposals WHERE thread_id = ? AND status != 'applied'", (thread_id,))
            c.execute('DELETE FROM receipt_assets WHERE thread_id=? AND transaction_id IS NULL', (thread_id,))
            c.execute('DELETE FROM agent_threads WHERE id = ?', (thread_id,))
