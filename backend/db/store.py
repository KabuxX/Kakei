"""SQLite storage for the local Kakei API."""

import copy
import sqlite3
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Callable, Optional

from db.schema import ensure_schema
from db.trajectory_store import detach_trajectory_references, read_trajectory_day, read_trajectory_timeline, replace_trajectory
from services.trajectory_mutation import TrajectoryCommand
from services.trajectory_validation import validate_timeline
from services.validation import ValidationError, normalize_transaction
from transaction_datetime import assign_estimated_datetimes


class AlreadyInitialized(Exception):
    pass


class NotInitialized(Exception):
    pass


class TrajectoryNotFound(Exception):
    pass


class TrajectoryConflict(Exception):
    pass


def _trajectory_day(timeline: dict, date: str) -> dict | None:
    return next((day for day in timeline["days"] if day["date"] == date), None)


def _trajectory_event(day: dict, event_id: str) -> dict | None:
    return next((event for event in day["events"] if event["id"] == event_id), None)


def _sort_trajectory_day(day: dict) -> None:
    if all(event.get("timeEvidence", "legacy") == "legacy" for event in day["events"] if isinstance(event, dict)):
        day["events"].sort(key=lambda event: event.get("time", "") if isinstance(event, dict) and isinstance(event.get("time", ""), str) else "")
    positions = {event["id"]: index for index, event in enumerate(day["events"])
                 if isinstance(event, dict) and isinstance(event.get("id"), str)}
    day["legs"].sort(key=lambda leg: positions.get(leg.get("fromEventId"), -1)
                     if isinstance(leg, dict) and isinstance(leg.get("fromEventId"), str) else -1)


def _trajectory_edges_valid(day: dict) -> bool:
    positions = {event["id"]: index for index, event in enumerate(day["events"])}
    return all(positions.get(leg["fromEventId"], -2) + 1 == positions.get(leg["toEventId"], -1)
               for leg in day["legs"])


def _apply_trajectory_command(timeline: dict, command: TrajectoryCommand, action: str) -> dict | None:
    kind = command.kind
    day = _trajectory_day(timeline, command.date) if command.date else None
    if kind == "day":
        if action == "create":
            if day is not None:
                raise TrajectoryConflict("日付が重複しています。")
            day = {"date": command.date, **copy.deepcopy(command.data)}
            timeline["days"].append(day)
        elif day is None:
            raise TrajectoryNotFound("指定日が見つかりません。")
        elif action == "update":
            day.update(copy.deepcopy(command.data))
        else:
            timeline["days"].remove(day)
        if action != "delete":
            ids = [event.get("id") for event in day["events"] if isinstance(event, dict)]
            if len(ids) != len(set(item for item in ids if isinstance(item, str))):
                if all(isinstance(item, str) for item in ids):
                    raise TrajectoryConflict("イベントIDが重複しています。")
            other_ids = {event["id"] for other in timeline["days"] if other is not day
                         for event in other["events"]}
            if any(isinstance(item, str) and item in other_ids for item in ids):
                raise TrajectoryConflict("イベントIDが重複しています。")
            _sort_trajectory_day(day)
    elif kind == "place":
        places = timeline["places"]
        exists = command.id in places
        if action == "create" and exists:
            raise TrajectoryConflict("地点IDが重複しています。")
        if action != "create" and not exists:
            raise TrajectoryNotFound("地点が見つかりません。")
        if action == "delete":
            for current in timeline["days"]:
                if any(event["placeId"] == command.id for event in current["events"]):
                    raise TrajectoryConflict("参照中の地点は削除できません。")
                if any(command.id in leg.get("viaPlaceIds", []) for leg in current["legs"]):
                    raise TrajectoryConflict("参照中の地点は削除できません。")
            del places[command.id]
        else:
            places[command.id] = copy.deepcopy(command.data)
    else:
        if day is None:
            raise TrajectoryNotFound("指定日が見つかりません。")
        if kind == "event":
            if action != "delete":
                candidate = {"places": timeline["places"], "days": [{
                    "date": command.date,
                    "events": [{"id": command.id, **copy.deepcopy(command.data)}],
                    "legs": [],
                }]}
                try:
                    validate_timeline(candidate, require_complete=False)
                except ValueError as error:
                    raise ValidationError("trajectory", str(error)) from error
            event = _trajectory_event(day, command.id)
            if action == "create":
                if any(_trajectory_event(current, command.id) for current in timeline["days"]):
                    raise TrajectoryConflict("イベントIDが重複しています。")
                day["events"].append({"id": command.id, **copy.deepcopy(command.data)})
            elif event is None:
                raise TrajectoryNotFound("イベントが見つかりません。")
            elif action == "update":
                event.clear()
                event.update({"id": command.id, **copy.deepcopy(command.data)})
            else:
                if any(command.id in (leg["fromEventId"], leg["toEventId"]) for leg in day["legs"]):
                    raise TrajectoryConflict("区間が参照するイベントは削除できません。")
                day["events"].remove(event)
            _sort_trajectory_day(day)
            if not _trajectory_edges_valid(day):
                raise TrajectoryConflict("イベントの順序が既存区間と衝突します。")
        else:
            leg = next((item for item in day["legs"] if item["fromEventId"] == command.from_event_id
                        and item["toEventId"] == command.to_event_id), None)
            if action == "create":
                if leg is not None:
                    raise TrajectoryConflict("区間が重複しています。")
                leg = {"fromEventId": command.from_event_id,
                       "toEventId": command.to_event_id, **copy.deepcopy(command.data)}
                day["legs"].append(leg)
            elif leg is None:
                raise TrajectoryNotFound("区間が見つかりません。")
            elif action == "update":
                leg.clear()
                leg.update({"fromEventId": command.from_event_id,
                            "toEventId": command.to_event_id, **copy.deepcopy(command.data)})
            else:
                day["legs"].remove(leg)
            _sort_trajectory_day(day)

    if action == "delete":
        return None
    result = {"kind": kind}
    if command.date is not None:
        result["date"] = command.date
    if command.id is not None:
        result["id"] = command.id
    if command.from_event_id is not None:
        result["fromEventId"] = command.from_event_id
        result["toEventId"] = command.to_event_id
    if kind == "day":
        data = {"events": day["events"], "legs": day["legs"]}
    elif kind == "place":
        data = timeline["places"][command.id]
    elif kind == "event":
        data = {key: value for key, value in _trajectory_event(day, command.id).items() if key != "id"}
    else:
        data = {key: value for key, value in leg.items() if key not in ("fromEventId", "toEventId")}
    result["data"] = copy.deepcopy(data)
    return result


class Store:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connection() as connection:
            ensure_schema(connection)

    @contextmanager
    def _connection(self):
        connection = sqlite3.connect(str(self.db_path), timeout=10)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("PRAGMA foreign_keys = ON")
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
                (id, title, date, type, category, amount, merchant, payment_method, time_estimated)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            record["id"], record["title"], record["date"], record["type"],
            record["category"], record["amount"], record.get("merchant"),
            record.get("paymentMethod"), int(record["timeEstimated"]),
        ))
        connection.executemany("""
            INSERT INTO transaction_items (transaction_id, position, name, amount)
            VALUES (?, ?, ?, ?)
        """, (
            (record["id"], position, item["name"], item["amount"])
            for position, item in enumerate(record.get("items", []))
        ))

    @staticmethod
    def _record(row, items: list[dict]) -> dict:
        result = {
            "id": row["id"], "title": row["title"], "date": row["date"],
            "type": row["type"], "category": row["category"], "amount": row["amount"],
            "timeEstimated": bool(row["time_estimated"]),
        }
        if row["type"] == "expense":
            result.update({
                "merchant": row["merchant"], "paymentMethod": row["payment_method"],
                "items": items,
            })
        return result

    def is_initialized(self):
        with self._connection() as connection:
            return self._initialized(connection)

    def sync_trajectory(self, timeline: dict) -> None:
        validate_timeline(timeline)
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            replace_trajectory(connection, timeline)

    def seed_trajectory_once(self, load_seed: Callable[[], dict]) -> None:
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            if connection.execute("SELECT 1 FROM meta WHERE key = 'trajectory_seeded'").fetchone():
                return
            has_days = connection.execute("SELECT 1 FROM trajectory_days LIMIT 1").fetchone()
            has_places = connection.execute("SELECT 1 FROM trajectory_places LIMIT 1").fetchone()
            if not has_days and not has_places:
                timeline = load_seed()
                validate_timeline(timeline)
                replace_trajectory(connection, timeline)
            connection.execute("INSERT INTO meta (key, value) VALUES ('trajectory_seeded', '1')")

    def get_trajectory_day(self, date: str) -> Optional[dict]:
        with self._connection() as connection:
            connection.execute("BEGIN")
            return read_trajectory_day(connection, date)

    def list_trajectory_dates(self) -> list[str]:
        with self._connection() as connection:
            return [row["date"] for row in connection.execute("SELECT date FROM trajectory_days ORDER BY date")]

    def mutate_trajectory(self, command: TrajectoryCommand, action: str) -> dict | None:
        if action not in ("create", "update", "delete"):
            raise ValueError("unknown trajectory action")
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            timeline = read_trajectory_timeline(connection)
            result = _apply_trajectory_command(timeline, command, action)
            try:
                validate_timeline(timeline, require_complete=False)
            except ValueError as error:
                raise ValidationError("trajectory", str(error)) from error
            for day in timeline['days']:
                for event in day['events']:
                    if event.get('timeEvidence') == 'exact' and event.get('transactionId'):
                        row = connection.execute('SELECT time_estimated FROM transactions WHERE id=?', (event['transactionId'],)).fetchone()
                        if row and row[0]:
                            raise ValidationError('timeEvidence', '仮設定の取引時刻は確定時刻として扱えません。')
            replace_trajectory(connection, timeline)
            connection.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('trajectory_seeded', '1')")
            connection.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('trajectory_modified', '1')")
            return result

    def initialize(self, records):
        if not isinstance(records, list):
            raise ValidationError("transactions", "取引の配列を指定してください。")
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            if self._initialized(connection):
                raise AlreadyInitialized()
            seen = set()
            normalized_records = []
            for index, record in enumerate(records):
                try:
                    normalized = normalize_transaction(record, import_mode=True)
                    if normalized["id"] in seen:
                        raise ValidationError("id", "IDが重複しています。")
                    seen.add(normalized["id"])
                    normalized_records.append(normalized)
                except ValidationError as error:
                    record_id = record.get("id") if isinstance(record, dict) else None
                    raise ValidationError(error.field, f"取引{index + 1}（ID: {record_id}）: {error.message}") from error
            try:
                normalized_records = assign_estimated_datetimes(normalized_records)
            except ValueError as error:
                raise ValidationError("date", "同じ日付の取引には一意な時刻を割り当てられません。") from error
            for record in normalized_records:
                self._insert(connection, record)
            connection.execute("INSERT INTO meta (key, value) VALUES ('initialized', '1')")
            return len(records)

    def list_transactions(self):
        with self._connection() as connection:
            connection.execute("BEGIN")
            self._require_initialized(connection)
            rows = connection.execute("SELECT * FROM transactions ORDER BY date DESC, id DESC").fetchall()
            items_by_transaction = {}
            for item in connection.execute("""
                SELECT transaction_id, name, amount
                FROM transaction_items ORDER BY transaction_id, position
            """):
                items_by_transaction.setdefault(item["transaction_id"], []).append({
                    "name": item["name"], "amount": item["amount"],
                })
            return [self._record(row, items_by_transaction.get(row["id"], [])) for row in rows]

    def get_transaction(self, transaction_id: str) -> Optional[dict]:
        with self._connection() as connection:
            connection.execute("BEGIN")
            self._require_initialized(connection)
            row = connection.execute("SELECT * FROM transactions WHERE id = ?", (transaction_id,)).fetchone()
            if row is None:
                return None
            items = [
                {"name": item["name"], "amount": item["amount"]}
                for item in connection.execute("""
                    SELECT name, amount FROM transaction_items
                    WHERE transaction_id = ? ORDER BY position
                """, (transaction_id,))
            ]
            return self._record(row, items)

    def create_transaction(self, draft):
        normalized = normalize_transaction(draft)
        record = {"id": str(uuid.uuid4()), **normalized}
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._require_initialized(connection)
            self._insert(connection, record)
        return record

    @staticmethod
    def _update(connection, record):
        connection.execute("""
            UPDATE transactions SET title = ?, date = ?, type = ?, category = ?, amount = ?,
                merchant = ?, payment_method = ?, time_estimated = ? WHERE id = ?
        """, (record["title"], record["date"], record["type"], record["category"], record["amount"],
              record.get("merchant"), record.get("paymentMethod"), int(record["timeEstimated"]), record["id"]))
        connection.execute("DELETE FROM transaction_items WHERE transaction_id = ?", (record["id"],))
        connection.executemany("INSERT INTO transaction_items VALUES (?, ?, ?, ?)", (
            (record["id"], position, item["name"], item["amount"])
            for position, item in enumerate(record.get("items", []))
        ))

    def update_transaction(self, transaction_id: str, draft: object, *, confirm_time: bool = False) -> dict:
        if type(confirm_time) is not bool:
            raise ValidationError("confirmTime", "時刻の確認は true または false で指定してください。")
        normalized = normalize_transaction(draft)
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._require_initialized(connection)
            old = connection.execute("SELECT * FROM transactions WHERE id = ?", (transaction_id,)).fetchone()
            if old is None:
                raise TrajectoryNotFound("取引が見つかりません。")
            if old["date"] == normalized["date"] and not confirm_time:
                normalized["timeEstimated"] = bool(old["time_estimated"])
            from services.agent_changes import prepare_changes
            preview = prepare_changes(connection, [{"kind": "transaction.update",
                "identity": {"id": transaction_id},
                "data": {**normalized, "confirmTime": confirm_time}}])
            record = preview["after"][0]
            self._update(connection, record)
            return record

    def delete_transaction(self, transaction_id: str) -> bool:
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._require_initialized(connection)
            detach_trajectory_references(connection, {transaction_id})
            cursor = connection.execute("DELETE FROM transactions WHERE id = ?", (transaction_id,))
            return cursor.rowcount > 0

    def delete_samples(self) -> int:
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._require_initialized(connection)
            ids = {row["id"] for row in connection.execute("SELECT id FROM transactions WHERE substr(id, 1, 7) = 'sample-'")}
            detach_trajectory_references(connection, ids)
            cursor = connection.execute("DELETE FROM transactions WHERE substr(id, 1, 7) = 'sample-'")
            return cursor.rowcount

    def apply_agent_proposal(self, proposal_id: str, revision: int) -> dict:
        from services.agent_changes import apply_proposal
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._require_initialized(connection)
            return apply_proposal(connection, proposal_id, revision)
