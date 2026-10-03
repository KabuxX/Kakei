"""Serve Kakei's frontend and local JSON API with FastAPI."""

import os
from pathlib import Path

from config.runtime import require_supported_python

require_supported_python()

from config.environment import load_environment

load_environment()

from api.app import create_app
from config.paths import DEFAULT_DB_PATH, FRONT_DIST_DIR

app = create_app(
    Path(os.getenv("KAKEI_DB_PATH") or DEFAULT_DB_PATH),
    FRONT_DIST_DIR,
)
