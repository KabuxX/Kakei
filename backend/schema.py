"""Create the SQLite schema and migrate legacy JSON-backed items."""

import json
import sqlite3


def _create_transactions(connection: sqlite3.Connection, table_name: str) -> None:
    connection.execute(f"""
        CREATE TABLE {table_name} (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            date TEXT NOT NULL,
            type TEXT NOT NULL,
            category TEXT NOT NULL,
            amount INTEGER NOT NULL,
            merchant TEXT,
            payment_method TEXT
        )
    """)


def _create_items(connection: sqlite3.Connection) -> None:
    connection.execute("""
        CREATE TABLE IF NOT EXISTS transaction_items (
            transaction_id TEXT NOT NULL REFERENCES transactions(id) ON DELETE CASCADE,
            position INTEGER NOT NULL CHECK (position >= 0),
            name TEXT NOT NULL,
            amount INTEGER NOT NULL CHECK (amount > 0),
            PRIMARY KEY (transaction_id, position)
        )
    """)


def _legacy_items(row: tuple) -> list[tuple[str, int, str, int]]:
    transaction_id, kind, amount, raw_items = row
    try:
        items = json.loads(raw_items)
    except (TypeError, ValueError) as error:
        raise ValueError(f"Invalid items for transaction {transaction_id!r}") from error
    if not isinstance(items, list):
        raise ValueError(f"Invalid items for transaction {transaction_id!r}")
    result = []
    for position, item in enumerate(items):
        if (not isinstance(item, dict)
                or not isinstance(item.get("name"), str)
                or not item["name"].strip()
                or isinstance(item.get("amount"), bool)
                or not isinstance(item.get("amount"), int)
                or not 1 <= item["amount"] <= 999_999_999):
            raise ValueError(f"Invalid items for transaction {transaction_id!r}")
        result.append((transaction_id, position, item["name"], item["amount"]))
    if result and (kind != "expense" or sum(item[3] for item in result) != amount):
        raise ValueError(f"Invalid items for transaction {transaction_id!r}")
    return result


def ensure_schema(connection: sqlite3.Connection) -> None:
    """Create a fresh schema or atomically move legacy items into child rows.

    The caller enables foreign keys before calling and commits or rolls back.
    """
    connection.execute("BEGIN IMMEDIATE")
    connection.execute("""
        CREATE TABLE IF NOT EXISTS meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    """)
    columns = {row[1] for row in connection.execute("PRAGMA table_info(transactions)")}
    if not columns:
        _create_transactions(connection, "transactions")
        _create_items(connection)
        return
    if "items_json" not in columns:
        _create_items(connection)
        return

    legacy_rows = connection.execute(
        "SELECT id, type, amount, items_json FROM transactions"
    ).fetchall()
    item_rows = [item for row in legacy_rows for item in _legacy_items(tuple(row))]
    _create_transactions(connection, "transactions_new")
    connection.execute("""
        INSERT INTO transactions_new
            (id, title, date, type, category, amount, merchant, payment_method)
        SELECT id, title, date, type, category, amount, merchant, payment_method
        FROM transactions
    """)
    connection.execute("DROP TABLE transactions")
    connection.execute("ALTER TABLE transactions_new RENAME TO transactions")
    _create_items(connection)
    connection.executemany(
        "INSERT INTO transaction_items (transaction_id, position, name, amount) VALUES (?, ?, ?, ?)",
        item_rows,
    )
