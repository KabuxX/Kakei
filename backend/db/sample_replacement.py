"""Match, back up, and atomically replace saved sample rows."""

import sqlite3
from contextlib import closing
from pathlib import Path

from db.schema import ensure_schema
from db.store import Store
from db.trajectory_store import replace_trajectory
from transaction_datetime import parse_transaction_datetime


def _sample_date_signature(date: str, time_estimated: bool) -> str:
    """Compare estimates by calendar day, while preserving entered minutes."""
    parsed_date, _ = parse_transaction_datetime(date)
    return parsed_date[:10] if time_estimated else parsed_date


def _expected_samples(records: list[dict]) -> dict:
    return {
        record["id"]: (
            record["title"], _sample_date_signature(record["date"], record["timeEstimated"]),
            record["type"], record["category"],
            record["amount"], record.get("merchant"), record.get("paymentMethod"),
            int(record["timeEstimated"]),
            tuple((position, item["name"], item["amount"])
                  for position, item in enumerate(record.get("items", []))),
        ) for record in records
    }


def _current_samples(connection: sqlite3.Connection) -> dict:
    items = {}
    for row in connection.execute("""
        SELECT transaction_id, position, name, amount FROM transaction_items
        WHERE substr(transaction_id, 1, 7) = 'sample-' ORDER BY transaction_id, position
    """):
        items.setdefault(row[0], []).append(tuple(row[1:]))
    sample_rows = connection.execute("""
            SELECT id, title, date, type, category, amount, merchant, payment_method, time_estimated
            FROM transactions WHERE substr(id, 1, 7) = 'sample-'
        """).fetchall()
    return {
        row[0]: (
            row[1], _sample_date_signature(row[2], bool(row[8])), *row[3:],
            tuple(items.get(row[0], [])),
        )
        for row in sample_rows
    }


def replace_sample_rows(db_path: Path, backup_path: Path, old_records: list[dict],
                        new_records: list[dict], timeline: dict) -> dict[str, int]:
    """Back up and replace recognized samples, or resync an already-new DB.

    Each invocation requires a new backup filename, including safe reruns.
    """
    db_path = Path(db_path)
    backup_path = Path(backup_path)
    if not db_path.is_file():
        raise ValueError(f"existing database required: {db_path}")
    # mode=rw also prevents accidental creation if the file disappears after the check.
    with closing(sqlite3.connect(db_path.resolve().as_uri() + "?mode=rw", uri=True, timeout=10)) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        # Exclusive creation refuses existing files, directories, and dangling symlinks.
        with backup_path.open("xb"):
            pass
        with closing(sqlite3.connect(backup_path)) as backup:
            connection.backup(backup)
        try:
            # ensure_schema begins IMMEDIATE: schema changes, guard, transaction
            # replacement and trajectory replacement all share this transaction.
            ensure_schema(connection)
            if connection.execute("SELECT 1 FROM meta WHERE key = 'trajectory_modified'").fetchone():
                raise ValueError("trajectory has been edited through the API")
            current = _current_samples(connection)
            if current == _expected_samples(new_records):
                deleted = inserted = 0
            elif current == _expected_samples(old_records):
                deleted = connection.execute(
                    "DELETE FROM transactions WHERE substr(id, 1, 7) = 'sample-'"
                ).rowcount
                for record in new_records:
                    Store._insert(connection, record)
                inserted = len(new_records)
            else:
                raise ValueError("database sample rows do not match the saved old or new samples")
            replace_trajectory(connection, timeline)
            connection.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('trajectory_seeded', '1')")
            connection.commit()
        except Exception:
            connection.rollback()
            raise
    return {"deleted": deleted, "inserted": inserted, "days": len(timeline["days"])}
