"""Local receipt bytes and links. Pending uploads expire after one day."""
import time, uuid
from db.store import Store, TrajectoryNotFound
from db.agent_store import AgentStore

def metadata(row):
    return {'id':row['id'],'mimeType':row['mime_type'],'sha256':row['sha256'],'pageCount':row['page_count'],'createdAt':row['created_at']}

def cleanup(connection, now=None):
    return connection.execute('DELETE FROM receipt_assets WHERE expires_at IS NOT NULL AND expires_at <= ?', (time.time() if now is None else now,)).rowcount

class ReceiptStore:
    def __init__(self, db_path):self.store=Store(db_path)
    def create_pending(self, thread_id, file):
        with self.store._connection() as c:
            c.execute('BEGIN IMMEDIATE');cleanup(c);AgentStore._thread(c,thread_id)
            duplicates=[row[0] for row in c.execute('SELECT id FROM receipt_assets WHERE sha256=?',(file.sha256,))]
            existing=c.execute('SELECT * FROM receipt_assets WHERE thread_id=? AND sha256=? AND expires_at IS NOT NULL',(thread_id,file.sha256)).fetchone()
            if existing:return {**metadata(existing),'duplicateReceiptIds':duplicates}
            identifier=str(uuid.uuid4());now=time.time()
            c.execute('INSERT INTO receipt_assets VALUES (?,?,?,?,?,?,?,?,?)',(identifier,thread_id,file.mime_type,file.sha256,file.page_count,file.data,now,now+86400,None))
            return {**metadata(c.execute('SELECT * FROM receipt_assets WHERE id=?',(identifier,)).fetchone()),'duplicateReceiptIds':duplicates}
    def get_asset(self, receipt_id):
        with self.store._connection() as c:
            cleanup(c)
            row=c.execute('SELECT * FROM receipt_assets WHERE id=?',(receipt_id,)).fetchone()
            return dict(row) if row else None
    def expire_pending(self, now):
        with self.store._connection() as c:return cleanup(c,now.timestamp())

    @staticmethod
    def validate_pending(connection, receipt_ids, thread_id):
        from services.validation import ValidationError
        if not isinstance(receipt_ids,list) or len(receipt_ids)>8 or any(not isinstance(i,str) for i in receipt_ids) or len(set(receipt_ids))!=len(receipt_ids):
            raise ValidationError('receiptIds','レシートの指定を確認してください。')
        for identifier in receipt_ids:
            row=connection.execute('SELECT * FROM receipt_assets WHERE id=?',(identifier,)).fetchone()
            if not row or row['thread_id']!=thread_id or row['transaction_id'] or row['expires_at']<=time.time():
                raise ValidationError('receiptIds','この会話の有効な未保存レシートを指定してください。')

    @staticmethod
    def attach(connection, receipt_ids, transaction_id, thread_id):
        ReceiptStore.validate_pending(connection,receipt_ids,thread_id)
        for identifier in receipt_ids:
            connection.execute('UPDATE receipt_assets SET transaction_id=?, expires_at=NULL WHERE id=?',(transaction_id,identifier))

    def list_for_transaction(self, transaction_id):
        with self.store._connection() as c:
            if not c.execute('SELECT 1 FROM transactions WHERE id=?',(transaction_id,)).fetchone():
                raise TrajectoryNotFound('取引が見つかりません。')
            return [metadata(row) for row in c.execute('SELECT * FROM receipt_assets WHERE transaction_id=? ORDER BY created_at',(transaction_id,))]

    @staticmethod
    def validate_commands(connection, commands, thread_id):
        receipt_ids=[]
        for command in commands:
            ids=command['data'].get('receiptIds',[])
            ReceiptStore.validate_pending(connection,ids,thread_id)
            receipt_ids.extend(ids)
        ReceiptStore.validate_pending(connection,receipt_ids,thread_id)

    @staticmethod
    def discard_proposal(connection, commands):
        for command in commands:
            for identifier in command['data'].get('receiptIds',[]):
                connection.execute('DELETE FROM receipt_assets WHERE id=? AND transaction_id IS NULL',(identifier,))
