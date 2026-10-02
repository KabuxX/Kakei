"""Repository paths independent of the process working directory."""

from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
FRONT_DIST_DIR = BACKEND_DIR.parent / "front" / "dist"
SAMPLE_DATA_DIR = BACKEND_DIR.parent / "front" / "src" / "data"
DEFAULT_DB_PATH = BACKEND_DIR / "data" / "kakei.sqlite3"
TIMELINE_PATH = SAMPLE_DATA_DIR / "september-timeline.json"
