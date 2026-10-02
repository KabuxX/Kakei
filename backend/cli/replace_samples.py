"""Guarded, one-time replacement of local SQLite sample transactions."""

import argparse
import json
import sqlite3
from pathlib import Path

from config.paths import SAMPLE_DATA_DIR
from services.sample_replacement import replace_samples


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, required=True, help="existing SQLite database")
    parser.add_argument("--backup", type=Path, required=True, help="new SQLite backup filename")
    arguments = parser.parse_args()
    try:
        result = replace_samples(arguments.db, SAMPLE_DATA_DIR / "old-samples.json",
                                 SAMPLE_DATA_DIR / "september-transactions.json",
                                 SAMPLE_DATA_DIR / "september-timeline.json", arguments.backup)
    except (OSError, ValueError, sqlite3.Error) as error:
        parser.exit(status=1, message=f"sample replacement failed: {error}\n")
    print(json.dumps(result))
