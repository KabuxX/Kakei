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


def _create_trajectory_tables(connection: sqlite3.Connection) -> None:
    connection.execute("""
        CREATE TABLE IF NOT EXISTS trajectory_places (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            address TEXT NOT NULL,
            longitude REAL NOT NULL CHECK (longitude BETWEEN 139.4 AND 140.1),
            latitude REAL NOT NULL CHECK (latitude BETWEEN 35.4 AND 35.9),
            source_url TEXT NOT NULL
        )
    """)
    connection.execute("""
        CREATE TABLE IF NOT EXISTS trajectory_days (
            date TEXT PRIMARY KEY
        )
    """)
    connection.execute("""
        CREATE TABLE IF NOT EXISTS trajectory_events (
            id TEXT PRIMARY KEY,
            day_date TEXT NOT NULL REFERENCES trajectory_days(date) ON DELETE CASCADE,
            position INTEGER NOT NULL CHECK (position >= 0),
            time TEXT NOT NULL,
            place_id TEXT NOT NULL REFERENCES trajectory_places(id),
            transaction_id TEXT,
            UNIQUE (day_date, position)
        )
    """)
    connection.execute("""
        CREATE TABLE IF NOT EXISTS trajectory_legs (
            day_date TEXT NOT NULL REFERENCES trajectory_days(date) ON DELETE CASCADE,
            position INTEGER NOT NULL CHECK (position >= 0),
            from_event_id TEXT NOT NULL REFERENCES trajectory_events(id),
            to_event_id TEXT NOT NULL REFERENCES trajectory_events(id),
            mode_hint TEXT,
            transport_transaction_id TEXT,
            has_via_places INTEGER NOT NULL CHECK (has_via_places IN (0, 1)),
            PRIMARY KEY (day_date, position)
        )
    """)
    connection.execute("""
        CREATE TABLE IF NOT EXISTS trajectory_leg_via_places (
            day_date TEXT NOT NULL,
            leg_position INTEGER NOT NULL,
            via_position INTEGER NOT NULL CHECK (via_position >= 0),
            place_id TEXT NOT NULL REFERENCES trajectory_places(id),
            PRIMARY KEY (day_date, leg_position, via_position),
            FOREIGN KEY (day_date, leg_position)
                REFERENCES trajectory_legs(day_date, position) ON DELETE CASCADE
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
    _create_trajectory_tables(connection)
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
