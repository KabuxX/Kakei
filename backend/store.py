"""SQLite storage for the local Kakei API."""

import json
import sqlite3
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Optional

from validation import ValidationError, normalize_transaction


class AlreadyInitialized(Exception):
    pass


class NotInitialized(Exception):
    pass


class Store:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connection() as connection:
            connection.execute("""
                CREATE TABLE IF NOT EXISTS meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
            """)
            connection.execute("""
                CREATE TABLE IF NOT EXISTS transactions (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    date TEXT NOT NULL,
                    type TEXT NOT NULL,
                    category TEXT NOT NULL,
                    amount INTEGER NOT NULL,
                    merchant TEXT,
                    payment_method TEXT,
                    items_json TEXT NOT NULL
                )
            """)

    @contextmanager
    def _connection(self):
        connection = sqlite3.connect(str(self.db_path), timeout=10)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    @staticmethod
    def _initialized(connection):
        return connection.execute("SELECT 1 FROM meta WHERE key = 'initialized'").fetchone() is not None

    @classmethod
    def _require_initialized(cls, connection):
        if not cls._initialized(connection):
            raise NotInitialized()

    @staticmethod
    def _insert(connection, record):
        connection.execute("""
            INSERT INTO transactions
                (id, title, date, type, category, amount, merchant, payment_method, items_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            record["id"], record["title"], record["date"], record["type"],
            record["category"], record["amount"], record.get("merchant"),
            record.get("paymentMethod"), json.dumps(record.get("items", []), ensure_ascii=False),
        ))

    @staticmethod
    def _record(row):
        result = {
            "id": row["id"], "title": row["title"], "date": row["date"],
            "type": row["type"], "category": row["category"], "amount": row["amount"],
        }
        if row["type"] == "expense":
            result.update({
                "merchant": row["merchant"], "paymentMethod": row["payment_method"],
                "items": json.loads(row["items_json"]),
            })
        return result

    def is_initialized(self):
        with self._connection() as connection:
            return self._initialized(connection)

    def initialize(self, records):
        if not isinstance(records, list):
            raise ValidationError("transactions", "取引の配列を指定してください。")
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            if self._initialized(connection):
                raise AlreadyInitialized()
            seen = set()
            for index, record in enumerate(records):
                try:
                    normalized = normalize_transaction(record, import_mode=True)
                    if normalized["id"] in seen:
                        raise ValidationError("id", "IDが重複しています。")
                    seen.add(normalized["id"])
                    self._insert(connection, normalized)
                except ValidationError as error:
                    record_id = record.get("id") if isinstance(record, dict) else None
                    raise ValidationError(error.field, f"取引{index + 1}（ID: {record_id}）: {error.message}") from error
            connection.execute("INSERT INTO meta (key, value) VALUES ('initialized', '1')")
            return len(records)

    def list_transactions(self):
        with self._connection() as connection:
            self._require_initialized(connection)
            rows = connection.execute("SELECT * FROM transactions ORDER BY date DESC, id DESC").fetchall()
            return [self._record(row) for row in rows]

    def get_transaction(self, transaction_id: str) -> Optional[dict]:
        with self._connection() as connection:
            self._require_initialized(connection)
            row = connection.execute("SELECT * FROM transactions WHERE id = ?", (transaction_id,)).fetchone()
            return self._record(row) if row else None

    def create_transaction(self, draft):
        normalized = normalize_transaction(draft)
        record = {"id": str(uuid.uuid4()), **normalized}
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._require_initialized(connection)
            self._insert(connection, record)
        return record

    def delete_transaction(self, transaction_id: str) -> bool:
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._require_initialized(connection)
            cursor = connection.execute("DELETE FROM transactions WHERE id = ?", (transaction_id,))
            return cursor.rowcount > 0

    def delete_samples(self) -> int:
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._require_initialized(connection)
            cursor = connection.execute("DELETE FROM transactions WHERE id LIKE 'sample-%'")
            return cursor.rowcount
