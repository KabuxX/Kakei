import copy
import json
import sqlite3
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from db.store import Store


FIXTURE = Path(__file__).resolve().parents[2] / "front" / "src" / "data" / "september-timeline.json"


class TrajectoryStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = Path(self.temp.name) / "kakei.sqlite3"
        self.store = Store(self.db)

    def timeline(self):
        return json.loads(FIXTURE.read_text(encoding="utf-8"))

    def expected_day_payload(self, timeline, day):
        place_ids = {event["placeId"] for event in day["events"]}
        place_ids.update(place_id for leg in day["legs"] for place_id in leg.get("viaPlaceIds", []))
        return {
            "places": {place_id: place for place_id, place in timeline["places"].items() if place_id in place_ids},
            "days": [day],
        }

    def test_sync_round_trips_all_days(self):
        timeline = self.timeline()
        self.store.sync_trajectory(timeline)

        for day in timeline["days"]:
            with self.subTest(date=day["date"]):
                self.assertEqual(self.store.get_trajectory_day(day["date"]), self.expected_day_payload(timeline, day))
        self.assertIsNone(self.store.get_trajectory_day("2026-10-01"))
        self.assertFalse(self.store.is_initialized())
        with closing(sqlite3.connect(self.db)) as connection:
            counts = tuple(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in (
                "trajectory_places", "trajectory_days", "trajectory_events", "trajectory_legs"
            ))
        self.assertEqual(counts, (10, 12, 36, 24))

    def test_optional_via_places_round_trip(self):
        timeline = self.timeline()
        day = timeline["days"][-2]
        day["legs"][1]["viaPlaceIds"] = []
        day["legs"][2]["viaPlaceIds"] = ["jrShibuya", "shibuyaMuji"]

        self.store.sync_trajectory(timeline)
        result = self.store.get_trajectory_day(day["date"])
        self.assertEqual(result, self.expected_day_payload(timeline, day))
        self.assertNotIn("viaPlaceIds", result["days"][0]["legs"][0])
        self.assertEqual(result["days"][0]["legs"][1]["viaPlaceIds"], [])
        self.assertEqual(result["days"][0]["legs"][2]["viaPlaceIds"], ["jrShibuya", "shibuyaMuji"])
        self.assertIn("shibuyaMuji", result["places"])

    def test_resync_replaces_only_trajectory_data(self):
        record = {"id": "kept-transaction", "title": "給与", "date": "2026-09-01",
                  "type": "income", "category": "収入", "amount": 100}
        sample = {**record, "id": "sample-deleted", "title": "旧サンプル"}
        self.store.initialize([record, sample])
        self.assertEqual(self.store.delete_samples(), 1)
        before_transactions = self.store.list_transactions()
        timeline = self.timeline()
        timeline["places"]["unused"] = copy.deepcopy(timeline["places"]["shibuyaMuji"])
        self.store.sync_trajectory(timeline)

        updated = copy.deepcopy(timeline)
        del updated["places"]["unused"]
        removed_date = updated["days"].pop()["date"]
        updated["places"]["shibuyaStarbucks"]["name"] = "更新された店舗"
        added_day = copy.deepcopy(updated["days"][0])
        added_day["date"] = "2026-10-01"
        for event in added_day["events"]:
            event["id"] = event["id"].replace("2026-09-19", "2026-10-01")
            event.pop("transactionId", None)
        for leg in added_day["legs"]:
            leg["fromEventId"] = leg["fromEventId"].replace("2026-09-19", "2026-10-01")
            leg["toEventId"] = leg["toEventId"].replace("2026-09-19", "2026-10-01")
        updated["days"].append(added_day)

        for _ in range(2):
            self.store.sync_trajectory(updated)
            self.assertIsNone(self.store.get_trajectory_day(removed_date))
            self.assertEqual(self.store.get_trajectory_day("2026-10-01"), self.expected_day_payload(updated, added_day))
            self.assertEqual(self.store.list_transactions(), before_transactions)
            with closing(sqlite3.connect(self.db)) as connection:
                self.assertIsNone(connection.execute("SELECT id FROM trajectory_places WHERE id = 'unused'").fetchone())
                self.assertEqual(connection.execute("SELECT value FROM meta WHERE key = 'initialized'").fetchone()[0], "1")

    def test_invalid_fixture_and_insert_failure_roll_back(self):
        timeline = self.timeline()
        self.store.sync_trajectory(timeline)
        original = self.store.get_trajectory_day("2026-09-19")

        invalid = copy.deepcopy(timeline)
        invalid["days"][0]["events"][0]["placeId"] = "unknown"
        with self.assertRaises(ValueError):
            self.store.sync_trajectory(invalid)
        self.assertEqual(self.store.get_trajectory_day("2026-09-19"), original)

        with closing(sqlite3.connect(self.db)) as connection:
            connection.execute("""
                CREATE TRIGGER fail_trajectory_insert BEFORE INSERT ON trajectory_events
                BEGIN SELECT RAISE(ABORT, 'blocked'); END
            """)
            connection.commit()
        modified = copy.deepcopy(timeline)
        modified["places"]["shibuyaStarbucks"]["name"] = "部分更新されてはいけない"
        with self.assertRaises(sqlite3.DatabaseError):
            self.store.sync_trajectory(modified)
        self.assertEqual(self.store.get_trajectory_day("2026-09-19"), original)


if __name__ == "__main__":
    unittest.main()
