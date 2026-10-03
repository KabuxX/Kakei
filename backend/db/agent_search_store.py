"""Durable bounded search evidence, independent of proposals and model success."""
import copy
import json
import time
import uuid
from db.store import Store, TrajectoryConflict, TrajectoryNotFound
from services.validation import ValidationError
from agent.place_contracts import END_STATES


def encoded(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False)


def size(value):
    return len(encoded(value).encode())


def bound(value, maximum):
    """Keep identifying fields, trim long strings and arrays with explicit notice."""
    out = copy.deepcopy(value)
    removed = 0
    while size(out) > maximum:
        choices = []
        def scan(node):
            if isinstance(node, dict):
                for k, v in node.items():
                    if isinstance(v, str) and len(v.encode()) > 100:
                        choices.append((len(v.encode()), node, k, v))
                    elif isinstance(v, list) and v:
                        choices.append((size(v), node, k, v))
                    if isinstance(v, (dict, list)): scan(v)
            elif isinstance(node, list):
                for v in node: scan(v)
        scan(out)
        if not choices: raise ValidationError('search', '検索記録が大きすぎます。')
        _, parent, key, val = max(choices, key=lambda x:x[0])
        if isinstance(val, list): val.pop(); removed += 1
        else: parent[key] = val[:max(1,len(val)//2)]; removed += 1
        if isinstance(out, dict): out.update(truncated=True, omitted=removed)
    return out


def bounded_candidates(node):
    if isinstance(node, dict):
        for k,v in list(node.items()):
            if k == 'candidates' and isinstance(v,list):
                node[k] = [bound(c,2048) for c in v[:20]]
                if len(v)>20 or any(c.get('truncated') for c in node[k]): node['truncated']=True
            else: bounded_candidates(v)
    elif isinstance(node,list):
        for v in node: bounded_candidates(v)


def cancel_searches(connection, context, *, now):
    rows=connection.execute("SELECT id,attempts_json FROM agent_place_searches WHERE thread_id=? AND client_message_id=? AND run_token=? AND status='running'", tuple(context[k] for k in ('thread_id','client_message_id','run_token'))).fetchall()
    for row in rows:
        attempts=json.loads(row['attempts_json'])
        for a in attempts:
            if a.get('status')=='running': a.update(status='cancelled',finishedAt=now)
        connection.execute("UPDATE agent_place_searches SET status='cancelled',finished_at=?,attempts_json=? WHERE id=?",(now,encoded(attempts),row['id']))


def recover_stale_turns(connection, *, now):
    rows=connection.execute("SELECT thread_id,client_message_id,token FROM agent_turns WHERE status='processing' AND started_at<=?",(now-70,)).fetchall()
    for r in rows:
        cancel_searches(connection,{'thread_id':r[0],'client_message_id':r[1],'run_token':r[2]},now=now)
    connection.execute("UPDATE agent_turns SET status='failed' WHERE status='processing' AND started_at<=?",(now-70,))


class AgentSearchStore:
    def __init__(self, db_path): self.store=Store(db_path)

    @staticmethod
    def _valid(c, context):
        row=c.execute('SELECT status,token FROM agent_turns WHERE thread_id=? AND client_message_id=?',(context['thread_id'],context['client_message_id'])).fetchone()
        if not row or row['status']!='processing' or row['token']!=context['run_token']:
            raise TrajectoryConflict('この検索処理は無効になりました。')

    def start(self, context, request):
        if size(request)>8192: raise ValidationError('search','検索条件が大きすぎます。')
        with self.store._connection() as c:
            c.execute('BEGIN IMMEDIATE'); self._valid(c,context)
            args=tuple(context[k] for k in ('thread_id','client_message_id','run_token'))
            seq=c.execute('SELECT COALESCE(MAX(sequence),0)+1 FROM agent_place_searches WHERE thread_id=? AND client_message_id=? AND run_token=?',args).fetchone()[0]
            sid=str(uuid.uuid4())
            c.execute("INSERT INTO agent_place_searches(id,thread_id,client_message_id,run_token,sequence,place_id,input_json,status,created_at) VALUES (?,?,?,?,?,?,?,'running',?)",(sid,*args,seq,request['place_id'],encoded(request),time.time()))
            return sid

    def _running(self,c,context,sid):
        self._valid(c,context)
        row=c.execute("SELECT * FROM agent_place_searches WHERE id=? AND thread_id=? AND client_message_id=? AND run_token=? AND status='running'",(sid,context['thread_id'],context['client_message_id'],context['run_token'])).fetchone()
        if not row: raise TrajectoryConflict('終了した検索は変更できません。')
        return row

    def record_attempt(self,context,search_id,attempt):
        with self.store._connection() as c:
            c.execute('BEGIN IMMEDIATE'); row=self._running(c,context,search_id)
            attempts=json.loads(row['attempts_json'])
            clean=copy.deepcopy(attempt); bounded_candidates(clean)
            index=next((i for i,a in enumerate(attempts) if a['id']==clean['id']),None)
            if index is None:
                if len(attempts)>=4: raise ValidationError('search','検索回数の上限です。')
                attempts.append(clean)
            else: attempts[index]=clean
            data=bound({'attempts':attempts},200*1024)
            c.execute('UPDATE agent_place_searches SET attempts_json=? WHERE id=?',(encoded(data['attempts']),search_id))

    def finish(self,context,search_id,result):
        if result.get('status') not in END_STATES: raise ValidationError('search','検索状態が不正です。')
        clean=copy.deepcopy(result); bounded_candidates(clean); clean=bound(clean,40*1024)
        with self.store._connection() as c:
            c.execute('BEGIN IMMEDIATE'); self._running(c,context,search_id)
            c.execute('UPDATE agent_place_searches SET result_json=?,status=?,finished_at=? WHERE id=?',(encoded(clean),clean['status'],time.time(),search_id))

    @staticmethod
    def _record(r):
        return {'searchId':r['id'],'createdAt':r['created_at'],'finishedAt':r['finished_at'],'input':json.loads(r['input_json']), 'attempts':json.loads(r['attempts_json']),'result':json.loads(r['result_json']) if r['result_json'] else None,'status':r['status'],'source':'search'}

    def get(self,thread_id,search_id):
        with self.store._connection() as c:
            row=c.execute('SELECT * FROM agent_place_searches WHERE id=? AND thread_id=?',(search_id,thread_id)).fetchone()
            if not row: raise TrajectoryNotFound('この会話の検索記録が見つかりません。')
            return self._record(row)

    def history(self,thread_id,*,search_id=None,before_id=None,limit=5):
        if type(limit) is not int or not 1<=limit<=10: raise ValidationError('limit','履歴は1〜10件で指定してください。')
        if search_id and before_id: raise ValidationError('search','IDとカーソルは同時指定できません。')
        if search_id: records=[self.get(thread_id,search_id)]
        else:
            with self.store._connection() as c:
                exists=c.execute('SELECT 1 FROM agent_place_searches WHERE thread_id=? LIMIT 1',(thread_id,)).fetchone()
                if exists:
                    args=[thread_id]; condition=''
                    if before_id:
                        r=c.execute('SELECT created_at,id FROM agent_place_searches WHERE id=? AND thread_id=?',(before_id,thread_id)).fetchone()
                        if not r: raise TrajectoryNotFound('履歴の位置が見つかりません。')
                        condition=' AND (created_at,id)<(?,?)'; args.extend(r)
                    records=[self._record(r) for r in c.execute('SELECT * FROM agent_place_searches WHERE thread_id=?'+condition+' ORDER BY created_at DESC,id DESC LIMIT ?',(*args,limit+1))]
                else:
                    records=[]
                    for r in c.execute('SELECT id,created_at,metadata_json FROM agent_proposals WHERE thread_id=? ORDER BY created_at DESC,id DESC',(thread_id,)):
                        for i,g in enumerate(json.loads(r['metadata_json']).get('placeCandidates',[])):
                            records.append({'searchId':None,'createdAt':r['created_at'],'finishedAt':None,'input':{'query':g.get('query','')},'attempts':[], 'result':g,'status':'legacy','source':'legacy_proposal','proposalId':r['id'],'legacyCursor':f"legacy:{r['id']}:{i}",'notice':'旧提案に残った最終候補。日時は提案作成時刻です。全検索履歴ではありません。'})
                    if before_id:
                        index=next((i for i,r in enumerate(records) if r['legacyCursor']==before_id),None)
                        if index is None: raise TrajectoryNotFound('履歴の位置が見つかりません。')
                        records=records[index+1:]
        page={'records':[],'nextBeforeId':None,'hasMore':False,'truncated':False}
        for r in records[:limit]:
            r=bound(r,28000)
            if size({**page,'records':page['records']+[r]})>32000: break
            page['records'].append(r); page['truncated'] |= bool(r.get('truncated'))
        page['hasMore']=len(records)>len(page['records'])
        if page['records']:
            last=page['records'][-1]; page['nextBeforeId']=last.get('searchId') or last.get('legacyCursor')
        return page

    def summary(self,thread_id):
        page=self.history(thread_id,limit=3)
        for r in page['records']: r.pop('attempts',None)
        return bound(page,8192)
