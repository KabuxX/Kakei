from trajectory_evidence_fixture import legacy_evidence
import copy
import json
import sqlite3
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from db.store import Store, TrajectoryConflict, TrajectoryNotFound
from services.trajectory_mutation import parse_trajectory_command
from services.validation import ValidationError


FIXTURE = Path(__file__).resolve().parents[2] / "front" / "src" / "data" / "september-timeline.json"


class TrajectoryStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = Path(self.temp.name) / "kakei.sqlite3"
        self.store = Store(self.db)

    def timeline(self):
        return legacy_evidence(json.loads(FIXTURE.read_text(encoding="utf-8")))

    def expected_day_payload(self, timeline, day):
        place_ids = {event["placeId"] for event in day["events"]}
        place_ids.update(place_id for leg in day["legs"] for place_id in leg.get("viaPlaceIds", []))
        return {
            "places": {place_id: place for place_id, place in timeline["places"].items() if place_id in place_ids},
            "days": [day],
        }

    def mutate(self, method, payload):
        action = {"POST": "create", "PUT": "update", "DELETE": "delete"}[method]
        return self.store.mutate_trajectory(parse_trajectory_command(payload, method), action)

    def place_data(self, name="新しい場所"):
        return {"name": name, "address": "東京都渋谷区渋谷1-1-1",
                "coordinates": [139.7, 35.65], "sourceUrl": "https://example.com/place"}

    def test_mutate_each_kind_round_trip(self):
        date = "2026-10-03"
        place = self.place_data()
        self.assertEqual(self.mutate("POST", {"kind": "place", "id": "new-place", "data": place}),
                         {"kind": "place", "id": "new-place", "data": place})
        self.mutate("POST", {"kind": "day", "date": date, "data": {"events": [], "legs": []}})
        self.assertEqual(self.store.get_trajectory_day(date), {"places": {}, "days": [{"date": date, "events": [], "legs": []}]})
        for event_id, time in (("visit-1", "09:00"), ("visit-2", "10:00")):
            self.mutate("POST", {"kind": "event", "date": date, "id": event_id,
                                 "data": {"time": time, "placeId": "new-place"}})
        self.mutate("POST", {"kind": "leg", "date": date, "fromEventId": "visit-1", "toEventId": "visit-2", "data": {}})
        self.assertEqual(self.store.get_trajectory_day(date)["days"][0]["legs"],
                         [{"fromEventId": "visit-1", "toEventId": "visit-2", "modeEvidence": "legacy", "modeEvidenceNote": None}])
        self.mutate("PUT", {"kind": "place", "id": "new-place", "data": self.place_data("更新した場所")})
        self.mutate("PUT", {"kind": "event", "date": date, "id": "visit-2", "data": {"time": "11:00", "placeId": "new-place"}})
        self.mutate("PUT", {"kind": "leg", "date": date, "fromEventId": "visit-1", "toEventId": "visit-2", "data": {"modeHint": "walk"}})
        saved = self.store.get_trajectory_day(date)
        self.assertEqual(saved["places"]["new-place"]["name"], "更新した場所")
        self.assertEqual(saved["days"][0]["events"][1]["time"], "11:00")
        self.assertEqual(saved["days"][0]["legs"][0]["modeHint"], "walk")
        self.mutate("DELETE", {"kind": "leg", "date": date, "fromEventId": "visit-1", "toEventId": "visit-2"})
        self.mutate("DELETE", {"kind": "event", "date": date, "id": "visit-1"})
        self.mutate("DELETE", {"kind": "event", "date": date, "id": "visit-2"})
        self.mutate("DELETE", {"kind": "day", "date": date})
        self.mutate("DELETE", {"kind": "place", "id": "new-place"})
        self.assertIsNone(self.store.get_trajectory_day(date))
        with closing(sqlite3.connect(self.db)) as connection:
            self.assertEqual(connection.execute("SELECT value FROM meta WHERE key = 'trajectory_modified'").fetchone()[0], "1")
            self.assertEqual(connection.execute("SELECT value FROM meta WHERE key = 'trajectory_seeded'").fetchone()[0], "1")

    def test_day_replacement_and_empty_day(self):
        date = "2026-10-03"
        self.mutate("POST", {"kind": "place", "id": "p", "data": self.place_data()})
        created_day = self.mutate("POST", {"kind": "day", "date": date, "data": {
            "events": [{"id": "later", "time": "11:00", "placeId": "p"},
                       {"id": "earlier", "time": "09:00", "placeId": "p"}],
            "legs": [{"fromEventId": "earlier", "toEventId": "later"}],
        }})
        self.assertEqual([event["id"] for event in created_day["data"]["events"]], ["earlier", "later"])
        updated = self.mutate("PUT", {"kind": "day", "date": date, "data": {"events": [], "legs": []}})
        self.assertEqual(updated["data"], {"events": [], "legs": []})
        self.assertEqual(self.store.get_trajectory_day(date), {"places": {}, "days": [{"date": date, "events": [], "legs": []}]})

    def test_optional_via_list_round_trip(self):
        date = "2026-10-03"
        self.mutate("POST", {"kind": "place", "id": "p", "data": self.place_data()})
        self.mutate("POST", {"kind": "day", "date": date, "data": {
            "events": [{"id": "a", "time": "09:00", "placeId": "p"},
                       {"id": "b", "time": "10:00", "placeId": "p"},
                       {"id": "c", "time": "11:00", "placeId": "p"}],
            "legs": [{"fromEventId": "b", "toEventId": "c", "viaPlaceIds": []}],
        }})
        saved_day = self.store.get_trajectory_day(date)
        self.assertEqual(saved_day["days"][0]["legs"][0]["viaPlaceIds"], [])
        with closing(sqlite3.connect(self.db)) as connection:
            self.assertEqual(connection.execute("SELECT position FROM trajectory_legs WHERE day_date = ?", (date,)).fetchone()[0], 1)

    def test_put_omission_removes_optional_field(self):
        self.store.sync_trajectory(self.timeline())
        self.mutate("PUT", {"kind": "event", "date": "2026-09-19", "id": "2026-09-19-1",
                            "data": {"time": "09:10", "placeId": "shibuyaStarbucks"}})
        event = self.store.get_trajectory_day("2026-09-19")["days"][0]["events"][0]
        self.assertNotIn("transactionId", event)

    def test_referenced_place_or_event_cannot_be_deleted(self):
        timeline = self.timeline()
        timeline["places"]["via-only"] = self.place_data()
        timeline["days"][0]["legs"][0]["viaPlaceIds"] = ["via-only"]
        self.store.sync_trajectory(timeline)
        before = self.store.get_trajectory_day("2026-09-19")
        for command in ({"kind": "place", "id": "via-only"},
                        {"kind": "event", "date": "2026-09-19", "id": "2026-09-19-1"}):
            with self.subTest(command=command), self.assertRaises(TrajectoryConflict):
                self.mutate("DELETE", command)
            self.assertEqual(self.store.get_trajectory_day("2026-09-19"), before)

    def test_event_insert_or_reorder_conflict_rolls_back(self):
        self.store.sync_trajectory(self.timeline())
        before = self.store.get_trajectory_day("2026-09-19")
        commands = (
            ("POST", {"kind": "event", "date": "2026-09-19", "id": "between",
                      "data": {"time": "11:00", "placeId": "shibuyaStarbucks"}}),
            ("PUT", {"kind": "event", "date": "2026-09-19", "id": "2026-09-19-2",
                     "data": {"time": "19:00", "placeId": "shibuyaMuji"}}),
        )
        for method, command in commands:
            with self.subTest(method=method), self.assertRaises(TrajectoryConflict):
                self.mutate(method, command)
            self.assertEqual(self.store.get_trajectory_day("2026-09-19"), before)

    def test_invalid_event_value_is_validation_error_before_edge_conflict(self):
        self.store.sync_trajectory(self.timeline())
        before = self.store.get_trajectory_day("2026-09-19")
        with self.assertRaises(ValidationError):
            self.mutate("POST", {"kind": "event", "date": "2026-09-19", "id": "invalid",
                                 "data": {"time": "11:00", "placeId": []}})
        self.assertEqual(self.store.get_trajectory_day("2026-09-19"), before)

    def test_duplicate_event_id_across_days(self):
        self.store.sync_trajectory(self.timeline())
        self.mutate("POST", {"kind": "day", "date": "2026-10-03", "data": {"events": [], "legs": []}})
        with self.assertRaises(TrajectoryConflict):
            self.mutate("POST", {"kind": "event", "date": "2026-10-03", "id": "2026-09-19-1",
                                 "data": {"time": "09:00", "placeId": "shibuyaStarbucks"}})
        self.assertEqual(self.store.get_trajectory_day("2026-10-03")["days"][0]["events"], [])

    def test_mutation_missing_and_invalid_references(self):
        with self.assertRaises(TrajectoryNotFound):
            self.mutate("PUT", {"kind": "day", "date": "2026-10-03", "data": {"events": [], "legs": []}})
        self.mutate("POST", {"kind": "day", "date": "2026-10-03", "data": {"events": [], "legs": []}})
        with self.assertRaises(ValidationError):
            self.mutate("POST", {"kind": "event", "date": "2026-10-03", "id": "e",
                                 "data": {"time": "09:00", "placeId": "missing"}})
        self.assertEqual(self.store.get_trajectory_day("2026-10-03")["days"][0]["events"], [])

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
