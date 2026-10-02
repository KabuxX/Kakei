"""Guarded, one-time replacement of local SQLite sample transactions."""

import argparse
import json
import sqlite3
from contextlib import closing
from pathlib import Path

from schema import ensure_schema
from store import Store
from trajectory_store import replace_trajectory
from trajectory_validation import load_timeline
from validation import normalize_transaction


DATA = Path(__file__).resolve().parents[1] / "front" / "src" / "data"


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_constant(value):
    raise ValueError(f"Invalid JSON number: {value}")


def _load_records(path: Path, *, unique_content: bool) -> list[dict]:
    with Path(path).open(encoding="utf-8") as source:
        records = json.load(source, object_pairs_hook=_unique_object, parse_constant=_reject_constant)
    if not isinstance(records, list) or not records:
        raise ValueError(f"{path}: nonempty transaction array required")
    seen_ids = set()
    seen_content = set()
    normalized_records = []
    for index, record in enumerate(records):
        label = f"{path}: transaction {index + 1}"
        if not isinstance(record, dict):
            raise ValueError(f"{label}: object required")
        fields = {"id", "title", "date", "type", "category", "amount"}
        if record.get("type") == "expense":
            fields.update({"merchant", "paymentMethod", "items"})
            if not isinstance(record.get("merchant"), str):
                raise ValueError(f"{label}: merchant string required")
            if not isinstance(record.get("paymentMethod"), str):
                raise ValueError(f"{label}: paymentMethod string required")
            items = record.get("items")
            if not isinstance(items, list) or any(
                not isinstance(item, dict) or item.keys() != {"name", "amount"}
                for item in items
            ):
                raise ValueError(f"{label}: complete items required")
        if record.keys() != fields:
            raise ValueError(f"{label}: complete transaction fields required")
        normalized = normalize_transaction(record, import_mode=True)
        # Import normalization is intentionally tolerant elsewhere; this command
        # must reject any input whose fields or items would be changed or dropped.
        if normalized != record:
            raise ValueError(f"{label}: normalization would change transaction data")
        transaction_id = normalized["id"]
        if not transaction_id.startswith("sample-") or transaction_id in seen_ids:
            raise ValueError(f"{label}: unique sample- ID required")
        seen_ids.add(transaction_id)
        content = json.dumps({key: value for key, value in normalized.items()
                              if key not in {"id", "date"}}, sort_keys=True, ensure_ascii=False)
        if unique_content and content in seen_content:
            raise ValueError(f"{label}: duplicate transaction content")
        seen_content.add(content)
        normalized_records.append(normalized)
    return normalized_records


def _check_transaction_references(timeline: dict, records: list[dict]) -> None:
    dates = {record["id"]: record["date"] for record in records}
    for day in timeline["days"]:
        for entries, field in ((day["events"], "transactionId"),
                               (day["legs"], "transportTransactionId")):
            for entry in entries:
                if field in entry and dates.get(entry[field]) != day["date"]:
                    raise ValueError(f"{day['date']}: {field} must reference a same-date transaction")


def _expected_samples(records: list[dict]) -> dict:
    return {
        record["id"]: (
            record["title"], record["date"], record["type"], record["category"],
            record["amount"], record.get("merchant"), record.get("paymentMethod"),
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
    return {
        row[0]: (*row[1:], tuple(items.get(row[0], [])))
        for row in connection.execute("""
            SELECT id, title, date, type, category, amount, merchant, payment_method
            FROM transactions WHERE substr(id, 1, 7) = 'sample-'
        """)
    }


def replace_samples(db_path: Path, old_path: Path, new_path: Path,
                    timeline_path: Path, backup_path: Path) -> dict[str, int]:
    """Back up an existing DB, then atomically replace only recognized samples.

    An already-new database keeps its transactions and resyncs trajectory rows.
    Each invocation requires a new backup filename, including safe reruns.
    """
    old_records = _load_records(old_path, unique_content=False)
    new_records = _load_records(new_path, unique_content=True)
    timeline = load_timeline(timeline_path)
    _check_transaction_references(timeline, new_records)
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
            connection.commit()
        except Exception:
            connection.rollback()
            raise
    return {"deleted": deleted, "inserted": inserted, "days": len(timeline["days"])}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, required=True, help="existing SQLite database")
    parser.add_argument("--backup", type=Path, required=True, help="new SQLite backup filename")
    arguments = parser.parse_args()
    try:
        result = replace_samples(arguments.db, DATA / "old-samples.json",
                                 DATA / "september-transactions.json",
                                 DATA / "september-timeline.json", arguments.backup)
    except (OSError, ValueError, sqlite3.Error) as error:
        parser.exit(status=1, message=f"sample replacement failed: {error}\n")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
