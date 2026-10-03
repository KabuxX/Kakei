"""Deterministic browser fixture; always uses disposable SQLite, never user data."""
import sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import uvicorn
from api.app import create_app

class BrowserRunner:
    async def run_turn(self, thread_id, messages, receipt_id=None):
        return {'text':'給与の追加案を作成しました。内容を確認してください。', 'commands':[{
            'kind':'transaction.create', 'identity':{}, 'data':{'title':'Agent 動作確認','date':'2026-09-30T12:00','type':'income','category':'収入','amount':12345}}]}

if __name__ == '__main__':
    with tempfile.TemporaryDirectory(prefix='kakei-agent-browser-') as directory:
        app = create_app(Path(directory)/'test.sqlite3', Path(__file__).resolve().parents[2]/'front/dist', port=8767, runner_factory=lambda store: BrowserRunner())
        uvicorn.run(app, host='127.0.0.1', port=8767, log_level='warning')
