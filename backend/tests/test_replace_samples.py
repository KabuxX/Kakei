from trajectory_evidence_fixture import legacy_evidence
import copy
import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cli.replace_samples import main
from services.sample_replacement import _check_transaction_references, replace_samples
from db.store import Store


ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "front" / "src" / "data"
OLD = DATA / "old-samples.json"
NEW = DATA / "september-transactions.json"
TIMELINE = DATA / "september-timeline.json"


class ReplaceSamplesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.db = self.directory / "kakei.sqlite3"
        self.backup = self.directory / "before.sqlite3"
        self.old_bytes = OLD.read_bytes()
        self.old = json.loads(self.old_bytes)
        self.new = json.loads(NEW.read_text(encoding="utf-8"))
        self.timeline = legacy_evidence(json.loads(TIMELINE.read_text(encoding="utf-8")))
        self.store = Store(self.db)
        self.store.initialize(self.old)
        self.user = self.store.create_transaction({
            "title": "利用者の買い物", "date": "2026-09-30T12:30", "type": "expense",
            "category": "日用品", "amount": 700, "merchant": "利用者の店",
            "paymentMethod": "cash", "items": [{"name": "品目", "amount": 700}],
        })
        # An existing trajectory must be replaced completely, including stale rows.
        stale = copy.deepcopy(self.timeline)
        stale["days"] = [stale["days"][0]]
        stale["places"]["unused"] = copy.deepcopy(next(iter(stale["places"].values())))
        self.store.sync_trajectory(stale)

    def snapshot(self, path=None):
        with closing(sqlite3.connect(path or self.db)) as connection:
            return list(connection.iterdump())

    def write_json(self, name, value):
        path = self.directory / name
        path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
        return path

    def write_legacy_database(self, path, records):
        with closing(sqlite3.connect(path)) as connection:
            connection.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
            connection.execute("INSERT INTO meta VALUES ('initialized', '1')")
            connection.execute("""
                CREATE TABLE transactions (
                    id TEXT PRIMARY KEY, title TEXT NOT NULL, date TEXT NOT NULL,
                    type TEXT NOT NULL, category TEXT NOT NULL, amount INTEGER NOT NULL,
                    merchant TEXT, payment_method TEXT, items_json TEXT NOT NULL
                )
            """)
            connection.executemany("""
                INSERT INTO transactions
                    (id, title, date, type, category, amount, merchant, payment_method, items_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, [
                (record["id"], record["title"], record["date"], record["type"],
                 record["category"], record["amount"], record.get("merchant"),
                 record.get("paymentMethod"), json.dumps(record.get("items", []), ensure_ascii=False))
                for record in records
            ])
            connection.commit()

    def assert_mixed_legacy_samples_replace(self, store, db_path):
        before_user = store.get_transaction("user-legacy-date")
        self.assertEqual(store.get_transaction("sample-0")["date"], "2026-09-28T12:40")
        self.assertIs(before_user["timeEstimated"], True)

        first_backup = self.directory / f"{db_path.stem}-before.sqlite3"
        self.assertEqual(replace_samples(
            db_path, OLD, NEW, TIMELINE, first_backup
        ), {"deleted": 16, "inserted": 37, "days": 12})
        self.assertEqual(store.get_transaction("user-legacy-date"), before_user)

        second_backup = self.directory / f"{db_path.stem}-rerun.sqlite3"
        self.assertEqual(replace_samples(
            db_path, OLD, NEW, TIMELINE, second_backup
        ), {"deleted": 0, "inserted": 0, "days": 12})
        self.assertEqual(store.get_transaction("user-legacy-date"), before_user)

    def test_replaces_samples_after_mixed_date_only_import_and_rerun(self):
        user = {
            "id": "user-legacy-date", "title": "古い買い物", "date": "2026-09-28",
            "type": "expense", "category": "日用品", "amount": 700,
            "merchant": "利用者の店", "paymentMethod": "cash",
            "items": [{"name": "品目", "amount": 700}],
        }
        db_path = self.directory / "mixed-import.sqlite3"
        store = Store(db_path)
        store.initialize([*self.old, user])

        self.assert_mixed_legacy_samples_replace(store, db_path)

    def test_replaces_samples_after_mixed_legacy_database_migration_and_rerun(self):
        user = {
            "id": "user-legacy-date", "title": "古い買い物", "date": "2026-09-28",
            "type": "expense", "category": "日用品", "amount": 700,
            "merchant": "利用者の店", "paymentMethod": "cash",
            "items": [{"name": "品目", "amount": 700}],
        }
        db_path = self.directory / "mixed-migration.sqlite3"
        self.write_legacy_database(db_path, [*self.old, user])
        store = Store(db_path)

        self.assert_mixed_legacy_samples_replace(store, db_path)

    def test_minute_transaction_date_matches_day_only_timeline_reference(self):
        timeline = {"days": [{
            "date": "2026-09-02",
            "events": [{"transactionId": "meal"}],
            "legs": [{"transportTransactionId": "train"}],
        }]}
        records = [
            {"id": "meal", "date": "2026-09-02T09:17"},
            {"id": "train", "date": "2026-09-02T10:30"},
        ]

        _check_transaction_references(timeline, records)

        with self.assertRaises(ValueError):
            _check_transaction_references(timeline, [{"id": "meal", "date": "2026-09-03T09:17"}])

    def run_replacement(self, **overrides):
        arguments = {"db_path": self.db, "old_path": OLD, "new_path": NEW,
                     "timeline_path": TIMELINE, "backup_path": self.backup}
        arguments.update(overrides)
        return replace_samples(**arguments)

    def assert_rejected_unchanged(self, **overrides):
        before = self.snapshot()
        with self.assertRaises((ValueError, OSError, sqlite3.DatabaseError)):
            self.run_replacement(**overrides)
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(OLD.read_bytes(), self.old_bytes)

    def assert_new_data(self):
        actual_by_id = {record["id"]: record for record in self.store.list_transactions()}
        for expected in [*self.new, self.user]:
            with self.subTest(transaction_id=expected["id"]):
                actual = actual_by_id.pop(expected["id"])
                self.assertEqual(actual["date"][:10], expected["date"][:10])
                expected_estimated = expected.get("timeEstimated", len(expected["date"]) == 10)
                self.assertIs(actual["timeEstimated"], expected_estimated)
                actual.pop("timeEstimated")
                actual["date"] = expected["date"]
                expected_fields = {key: value for key, value in expected.items()
                                   if key != "timeEstimated"}
                self.assertEqual(actual, expected_fields)
        self.assertEqual(actual_by_id, {})
        for day in self.timeline["days"]:
            place_ids = {event["placeId"] for event in day["events"]}
            place_ids.update(place_id for leg in day["legs"] for place_id in leg.get("viaPlaceIds", []))
            self.assertEqual(self.store.get_trajectory_day(day["date"]), {
                "days": [day], "places": {key: value for key, value in self.timeline["places"].items()
                                         if key in place_ids},
            })
        with closing(sqlite3.connect(self.db)) as connection:
            places = [row[0] for row in connection.execute("SELECT id FROM trajectory_places ORDER BY id")]
            dates = [row[0] for row in connection.execute("SELECT date FROM trajectory_days ORDER BY date")]
            self.assertEqual(places, sorted(self.timeline["places"]))
            self.assertEqual(dates, [f"2026-09-{day}" for day in range(19, 31)])
            self.assertEqual(connection.execute("SELECT value FROM meta WHERE key = 'initialized'").fetchone()[0], "1")
        self.assertEqual(OLD.read_bytes(), self.old_bytes)

    def test_replaces_old_samples_and_backs_up_every_original_row(self):
        before = self.snapshot()
        self.assertEqual(self.run_replacement(), {"deleted": 16, "inserted": 37, "days": 12})
        self.assertEqual(self.snapshot(self.backup), before)
        self.assert_new_data()

    def test_rerun_preserves_transactions_and_resyncs_trajectory(self):
        self.run_replacement()
        transactions_before = self.store.list_transactions()
        with closing(sqlite3.connect(self.db)) as connection:
            connection.execute("DELETE FROM trajectory_days")
            connection.commit()
        before = self.snapshot()
        second_backup = self.directory / "second.sqlite3"
        self.assertEqual(self.run_replacement(backup_path=second_backup),
                         {"deleted": 0, "inserted": 0, "days": 12})
        self.assertEqual(self.snapshot(second_backup), before)
        self.assertEqual(self.store.list_transactions(), transactions_before)
        self.assert_new_data()

    def test_replace_samples_rejects_api_modified_trajectory(self):
        with closing(sqlite3.connect(self.db)) as connection:
            connection.execute("INSERT INTO meta (key, value) VALUES ('trajectory_modified', '1')")
            connection.commit()
        before = self.snapshot()
        with self.assertRaisesRegex(ValueError, "edited"):
            replace_samples(self.db, OLD, NEW, TIMELINE, self.backup)
        self.assertEqual(self.snapshot(), before)

    def test_edited_missing_and_extra_sample_rows_are_rejected(self):
        for index, sql in enumerate((
            "UPDATE transactions SET title = 'edited' WHERE id = 'sample-1'",
            "UPDATE transaction_items SET name = 'edited' WHERE transaction_id = 'sample-1' AND position = 0",
            "UPDATE transactions SET merchant = 'unexpected' WHERE id = 'sample-0'",
            "UPDATE transactions SET date = '2026-09-29T12:00' WHERE id = 'sample-0'",
            "DELETE FROM transactions WHERE id = 'sample-1'",
            "INSERT INTO transactions (id, title, date, type, category, amount, merchant, payment_method) "
            "VALUES ('sample-extra', '余分', '2026-09-30', 'income', '収入', 100, NULL, NULL)",
        )):
            with self.subTest(sql=sql):
                self.db = self.directory / f"guard-{index}.sqlite3"
                self.store = Store(self.db)
                self.store.initialize([*self.old, self.user])
                with closing(sqlite3.connect(self.db)) as connection:
                    connection.execute("PRAGMA foreign_keys = ON")
                    connection.execute(sql)
                    connection.commit()
                backup = self.directory / f"rejected-{len(list(self.directory.iterdir()))}.sqlite3"
                self.assert_rejected_unchanged(backup_path=backup)

    def test_invalid_records_never_silently_drop_fields_or_items(self):
        mutations = (
            lambda rows: rows[0].update(extra="lost field"),
            lambda rows: rows[0].pop("merchant"),
            lambda rows: rows[0].update(paymentMethod="invalid"),
            lambda rows: rows[0].update(merchant=None),
            lambda rows: rows[0].update(items="invalid"),
            lambda rows: rows[0]["items"][0].update(amount=1),
            lambda rows: rows[0]["items"][0].update(extra="lost field"),
            lambda rows: rows[0]["items"][0].update(name=""),
            lambda rows: rows[0].update(title=" trimmed "),
            lambda rows: rows[0].update(id="user-id"),
            lambda rows: rows.append(copy.deepcopy(rows[0])),
            lambda rows: rows.append({**copy.deepcopy(rows[0]), "id": "sample-duplicate", "date": "2026-09-01"}),
        )
        for index, mutate in enumerate(mutations):
            with self.subTest(case=index):
                rows = copy.deepcopy(self.new)
                mutate(rows)
                self.assert_rejected_unchanged(new_path=self.write_json(f"invalid-{index}.json", rows))
                self.assertFalse(self.backup.exists())

    def test_null_payment_is_rejected_before_backup(self):
        rows = copy.deepcopy(self.new)
        rows[0]["paymentMethod"] = None
        self.assert_rejected_unchanged(new_path=self.write_json("null-payment.json", rows))
        self.assertFalse(self.backup.exists())

    def test_strict_json_rejects_malformed_duplicate_keys_and_nonfinite_numbers(self):
        for name in ("new_path", "old_path", "timeline_path"):
            for raw in ('{broken', '[{"id":"first","id":"second"}]', '[NaN]'):
                with self.subTest(input=name, raw=raw):
                    path = self.directory / "invalid.json"
                    path.write_text(raw, encoding="utf-8")
                    self.assert_rejected_unchanged(**{name: path})
                    self.assertFalse(self.backup.exists())

    def test_event_and_transport_references_require_an_existing_same_date_transaction(self):
        for field in ("transactionId", "transportTransactionId"):
            for transaction_id in ("missing", "sample-0"):
                with self.subTest(field=field, transaction_id=transaction_id):
                    timeline = copy.deepcopy(self.timeline)
                    day = timeline["days"][0]
                    target = day["events"][0] if field == "transactionId" else day["legs"][0]
                    target[field] = transaction_id
                    self.assert_rejected_unchanged(timeline_path=self.write_json("invalid-timeline.json", timeline))
                    self.assertFalse(self.backup.exists())

    def test_explicit_sample_datetime_must_match_exactly(self):
        records = copy.deepcopy(self.old)
        sample_zero = next(record for record in records if record["id"] == "sample-0")
        sample_zero["date"] = "2026-09-28T12:00"
        old_path = self.write_json("entered-old-samples.json", records)
        db_path = self.directory / "entered-sample.sqlite3"
        store = Store(db_path)
        store.initialize(records)
        with closing(sqlite3.connect(db_path)) as connection:
            connection.execute("UPDATE transactions SET date = ? WHERE id = ?",
                               ("2026-09-28T12:01", "sample-0"))
            connection.commit()
        before = self.snapshot(db_path)

        with self.assertRaises(ValueError):
            replace_samples(db_path, old_path, NEW, TIMELINE,
                            self.directory / "entered-sample-backup.sqlite3")

        self.assertEqual(self.snapshot(db_path), before)
        self.assertEqual(store.get_transaction("sample-0")["date"], "2026-09-28T12:01")

    def test_existing_backup_is_never_overwritten(self):
        self.backup.write_bytes(b"keep this backup")
        self.assert_rejected_unchanged()
        self.assertEqual(self.backup.read_bytes(), b"keep this backup")

    def test_missing_database_is_not_created(self):
        missing = self.directory / "missing.sqlite3"
        with self.assertRaises((ValueError, OSError, sqlite3.DatabaseError)):
            self.run_replacement(db_path=missing)
        self.assertFalse(missing.exists())
        self.assertFalse(self.backup.exists())

    def test_transaction_and_trajectory_insert_failures_roll_back_every_change(self):
        for table in ("transactions", "trajectory_events"):
            with self.subTest(table=table):
                with closing(sqlite3.connect(self.db)) as connection:
                    connection.execute(f"CREATE TRIGGER fail_insert BEFORE INSERT ON {table} "
                                       "BEGIN SELECT RAISE(ABORT, 'blocked'); END")
                    connection.commit()
                before = self.snapshot()
                backup = self.directory / f"{table}-failure.sqlite3"
                self.assert_rejected_unchanged(backup_path=backup)
                self.assertEqual(self.snapshot(backup), before)
                with closing(sqlite3.connect(self.db)) as connection:
                    connection.execute("DROP TRIGGER fail_insert")
                    connection.commit()

    def test_schema_creation_is_rolled_back_when_sample_guard_fails(self):
        with closing(sqlite3.connect(self.db)) as connection:
            connection.execute("PRAGMA foreign_keys = ON")
            for table in ("trajectory_leg_via_places", "trajectory_legs", "trajectory_events",
                          "trajectory_days", "trajectory_places"):
                connection.execute(f"DROP TABLE {table}")
            connection.execute("UPDATE transactions SET amount = amount + 1 WHERE id = 'sample-0'")
            connection.commit()
        self.assert_rejected_unchanged()

    def test_package_cli_uses_repository_json_defaults(self):
        from contextlib import redirect_stdout
        from io import StringIO
        from unittest.mock import patch

        output = StringIO()
        with patch.object(sys, "argv", ["replace_samples", "--db", str(self.db),
                                      "--backup", str(self.backup)]), redirect_stdout(output):
            main()
        self.assertEqual(json.loads(output.getvalue()), {"deleted": 16, "inserted": 37, "days": 12})
        self.assert_new_data()

    def test_cli_uses_repository_json_defaults_from_another_directory(self):
        result = subprocess.run([
            sys.executable, str(ROOT / "backend" / "replace_samples.py"),
            "--db", str(self.db), "--backup", str(self.backup),
        ], capture_output=True, text=True, cwd=self.directory)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), {"deleted": 16, "inserted": 37, "days": 12})
        self.assert_new_data()


if __name__ == "__main__":
    unittest.main()
