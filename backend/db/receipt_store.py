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
