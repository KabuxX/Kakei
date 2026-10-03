"""Bounded SELECT execution over explicitly public SQLite views."""

import json
import re
import sqlite3
import time
from pathlib import Path

from services.validation import ValidationError

PUBLIC_TABLES = {
    "agent_transactions": "transactions",
    "agent_transaction_items": "transaction_items",
    "agent_trajectory_days": "trajectory_days",
    "agent_trajectory_events": "trajectory_events",
    "agent_trajectory_legs": "trajectory_legs",
    "agent_trajectory_places": "trajectory_places",
}
FUNCTIONS = frozenset("count sum avg min max total coalesce ifnull nullif abs round length lower upper substr substring replace trim ltrim rtrim date datetime strftime julianday unixepoch".split())
# Strip comments and quoted text only to identify unsupported CTE syntax. SQLite
# still parses the statement; the authorizer and read-only handle enforce access.
QUOTED = re.compile(r"'(?:''|[^'])*'|\"(?:\"\"|[^\"])*\"|`(?:``|[^`])*`|\[[^\]]*\]|--[^\n]*|/\*.*?\*/", re.S)


def run_read_sql(db_path: Path, sql: str) -> list[dict]:
    if not isinstance(sql, str) or len(sql.encode("utf-8")) > 8192:
        raise ValidationError("sql", "SQLは8 KiB以内で指定してください。")
    tokens = re.findall(r"[A-Za-z_]+", QUOTED.sub(" ", sql).upper())
    if not tokens or tokens[0] != "SELECT" or "WITH" in tokens:
        raise ValidationError("sql", "CTEを使わない単一のSELECTを指定してください。")

    def authorize(action, first, second, database, source):
        if action == sqlite3.SQLITE_SELECT:
            return sqlite3.SQLITE_OK
        if action == sqlite3.SQLITE_FUNCTION and (second or "").lower() in FUNCTIONS:
            return sqlite3.SQLITE_OK
        if action == sqlite3.SQLITE_READ:
            if (first in PUBLIC_TABLES and database in ("main", None)) or (database == "main" and PUBLIC_TABLES.get(source) == first):
                return sqlite3.SQLITE_OK
        return sqlite3.SQLITE_DENY

    connection = sqlite3.connect(Path(db_path).resolve().as_uri() + "?mode=ro", uri=True, timeout=2)
    connection.row_factory = sqlite3.Row
    deadline = time.monotonic() + 2
    try:
        connection.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, 65536)
        connection.set_authorizer(authorize)
        connection.set_progress_handler(lambda: int(time.monotonic() >= deadline), 1000)
        cursor = connection.execute(sql)
        rows = []
        size = 2
        for row in cursor:
            item = dict(row)
            encoded = json.dumps(item, ensure_ascii=False, allow_nan=False).encode("utf-8")
            if size + len(encoded) + (2 if rows else 0) > 65536:
                break
            rows.append(item)
            size += len(encoded) + (2 if len(rows) > 1 else 0)
            if len(rows) == 100:
                break
        return rows
    except (sqlite3.Error, ValueError, TypeError) as error:
        raise ValidationError("sql", "SQLを実行できません。公開ビュー、許可された関数、2秒以内のSELECTを使用してください。") from error
    finally:
        connection.close()
