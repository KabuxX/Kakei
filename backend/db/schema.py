"""Create the SQLite schema and migrate legacy JSON-backed items."""

import json
import sqlite3

from transaction_datetime import assign_estimated_datetimes


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
            payment_method TEXT,
            time_estimated INTEGER NOT NULL DEFAULT 0 CHECK (time_estimated IN (0, 1))
        )
    """)


def _backfill_transaction_dates(connection: sqlite3.Connection) -> None:
    rows = connection.execute(
        "SELECT id, date, time_estimated FROM transactions ORDER BY id"
    ).fetchall()
    records = assign_estimated_datetimes([
        {"id": row[0], "date": row[1], "timeEstimated": bool(row[2])}
        for row in rows
    ])
    connection.executemany(
        "UPDATE transactions SET date = ?, time_estimated = ? WHERE id = ?",
        ((record["date"], int(record["timeEstimated"]), record["id"])
         for record in records),
    )


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


def _ensure_domain_schema(connection: sqlite3.Connection) -> None:
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
        if "time_estimated" not in columns:
            connection.execute("""
                ALTER TABLE transactions ADD COLUMN time_estimated INTEGER NOT NULL DEFAULT 0
                CHECK (time_estimated IN (0, 1))
            """)
        _backfill_transaction_dates(connection)
        _create_items(connection)
        return

    legacy_columns = "id, title, date, type, category, amount, merchant, payment_method, items_json"
    if "time_estimated" in columns:
        legacy_columns += ", time_estimated"
    legacy_rows = connection.execute(f"SELECT {legacy_columns} FROM transactions ORDER BY id").fetchall()
    records = assign_estimated_datetimes([
        {
            "id": row[0], "date": row[2],
            "timeEstimated": bool(row[9]) if len(row) > 9 else False,
        }
        for row in legacy_rows
    ])
    _create_transactions(connection, "transactions_new")
    connection.executemany("""
        INSERT INTO transactions_new
            (id, title, date, type, category, amount, merchant, payment_method, time_estimated)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        (row[0], row[1], record["date"], row[3], row[4], row[5], row[6], row[7],
         int(record["timeEstimated"]))
        for row, record in zip(legacy_rows, records)
    ))
    connection.execute("DROP VIEW IF EXISTS agent_transactions")
    connection.execute("DROP VIEW IF EXISTS agent_transaction_items")
    connection.execute("DROP TABLE transactions")
    connection.execute("ALTER TABLE transactions_new RENAME TO transactions")
    _create_items(connection)
    item_rows = [
        item for row in legacy_rows
        for item in _legacy_items((row[0], row[3], row[5], row[8]))
    ]
    connection.executemany(
        "INSERT INTO transaction_items (transaction_id, position, name, amount) VALUES (?, ?, ?, ?)",
        item_rows,
    )


def ensure_schema(connection: sqlite3.Connection) -> None:
    """Migrate domain tables before exposing public views in the same transaction."""
    _ensure_domain_schema(connection)
    _create_agent_tables(connection)
    for name in ('transactions', 'transaction_items', 'trajectory_days', 'trajectory_events', 'trajectory_legs', 'trajectory_places'):
        connection.execute(f'DROP VIEW IF EXISTS agent_{name}')
        # Prevent COUNT(*) view flattening from losing its authorizer context.
        connection.execute(f'CREATE VIEW agent_{name} AS SELECT * FROM {name} LIMIT -1 OFFSET 0')


def _create_agent_tables(connection: sqlite3.Connection) -> None:
    for statement in (
        '''CREATE TABLE IF NOT EXISTS agent_threads (
            id TEXT PRIMARY KEY, created_at REAL NOT NULL, title TEXT NOT NULL)''',
        '''CREATE TABLE IF NOT EXISTS agent_messages (
            id TEXT PRIMARY KEY, thread_id TEXT NOT NULL REFERENCES agent_threads(id) ON DELETE CASCADE,
            client_message_id TEXT NOT NULL, role TEXT NOT NULL CHECK(role IN ('user','assistant')),
            text TEXT NOT NULL, created_at REAL NOT NULL, UNIQUE(thread_id, client_message_id))''',
        '''CREATE TABLE IF NOT EXISTS agent_proposals (
            id TEXT PRIMARY KEY, thread_id TEXT REFERENCES agent_threads(id) ON DELETE SET NULL,
            revision INTEGER NOT NULL, status TEXT NOT NULL CHECK(status IN ('pending','applied','rejected','expired')),
            commands_json TEXT NOT NULL, baselines_json TEXT NOT NULL,
            created_at REAL NOT NULL, expires_at REAL NOT NULL, applied_at REAL,
            result_json TEXT, before_json TEXT NOT NULL DEFAULT '[]', after_json TEXT NOT NULL DEFAULT '[]',
            metadata_json TEXT NOT NULL DEFAULT '{}')''',
        '''CREATE TABLE IF NOT EXISTS receipt_assets (
            id TEXT PRIMARY KEY, thread_id TEXT REFERENCES agent_threads(id) ON DELETE SET NULL,
            mime_type TEXT NOT NULL, sha256 TEXT NOT NULL, page_count INTEGER NOT NULL, data BLOB NOT NULL,
            created_at REAL NOT NULL, expires_at REAL, transaction_id TEXT REFERENCES transactions(id) ON DELETE CASCADE)''',
        'CREATE INDEX IF NOT EXISTS receipt_hash ON receipt_assets(sha256)',
        '''CREATE TABLE IF NOT EXISTS agent_turns (
            thread_id TEXT NOT NULL REFERENCES agent_threads(id) ON DELETE CASCADE,
            client_message_id TEXT NOT NULL, input_json TEXT NOT NULL, token TEXT NOT NULL,
            status TEXT NOT NULL, started_at REAL NOT NULL, result_json TEXT,
            PRIMARY KEY(thread_id, client_message_id))''',
        'CREATE INDEX IF NOT EXISTS agent_messages_thread ON agent_messages(thread_id, created_at)',
        'CREATE INDEX IF NOT EXISTS agent_proposals_thread ON agent_proposals(thread_id, created_at)',
    ):
        connection.execute(statement)
