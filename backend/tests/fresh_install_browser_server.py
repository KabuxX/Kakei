"""Serve the shipped app with a fresh disposable DB and no sample fixtures."""

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import uvicorn
from api.app import create_app

if __name__ == '__main__':
    root = Path(__file__).resolve().parents[2]
    with tempfile.TemporaryDirectory(prefix='kakei-fresh-install-') as directory:
        app = create_app(Path(directory) / 'kakei.sqlite3', root / 'front/dist', port=8769)
        uvicorn.run(app, host='127.0.0.1', port=8769, log_level='warning')
