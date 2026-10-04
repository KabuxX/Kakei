"""Serve budget UI against a disposable DB without loading the user's .env."""

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import uvicorn
from api.app import create_app

if __name__ == '__main__':
    root = Path(__file__).resolve().parents[2]
    with tempfile.TemporaryDirectory(prefix='kakei-budget-browser-') as directory:
        app = create_app(Path(directory) / 'fixture.sqlite3', root / 'front/dist', port=8768)
        records = json.loads((root / 'front/src/data/september-transactions.json').read_text())
        app.state.store.initialize(records)
        uvicorn.run(app, host='127.0.0.1', port=8768, log_level='warning')
