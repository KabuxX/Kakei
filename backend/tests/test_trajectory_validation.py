import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from trajectory_validation import load_timeline, validate_timeline


FIXTURE = Path(__file__).resolve().parents[2] / "front" / "src" / "data" / "september-timeline.json"


class TrajectoryValidationTests(unittest.TestCase):
    def timeline(self):
        return json.loads(FIXTURE.read_text(encoding="utf-8"))

    def assert_invalid(self, timeline, context):
        with self.assertRaises(ValueError) as error:
            validate_timeline(timeline)
        self.assertIn(context, str(error.exception))

    def test_current_september_fixture_is_valid(self):
        timeline = load_timeline(FIXTURE)
        self.assertEqual((len(timeline["places"]), len(timeline["days"])), (10, 30))
        self.assertEqual(sum(len(day["events"]) for day in timeline["days"]), 120)
        self.assertEqual(sum(len(day["legs"]) for day in timeline["days"]), 90)
        self.assertEqual(validate_timeline(timeline), timeline)

    def test_duplicate_json_key_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            duplicate_key_path = Path(directory) / "timeline.json"
            duplicate_key_path.write_text('{"places":{"x":{},"x":{}},"days":[]}', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "duplicate"):
                load_timeline(duplicate_key_path)

    def test_rejects_unknown_fields_and_invalid_place_details(self):
        timeline = self.timeline()
        timeline["other"] = 1
        self.assert_invalid(timeline, "other")

        for field, value in (
            ("sourceUrl", "http://example.com"),
            ("coordinates", [140.2, 35.6]),
            ("coordinates", [float("nan"), 35.6]),
            ("name", " "),
        ):
            with self.subTest(field=field, value=value):
                timeline = self.timeline()
                timeline["places"]["shibuyaStarbucks"][field] = value
                self.assert_invalid(timeline, "shibuyaStarbucks")

        timeline = self.timeline()
        timeline["places"]["shibuyaStarbucks"]["other"] = 1
        self.assert_invalid(timeline, "other")

    def test_rejects_bad_day_date_and_duplicate_ids(self):
        timeline = self.timeline()
        timeline["days"][0]["date"] = "2026-09-31"
        self.assert_invalid(timeline, "date")

        timeline = self.timeline()
        timeline["days"].append(copy.deepcopy(timeline["days"][0]))
        self.assert_invalid(timeline, "date")

        timeline = self.timeline()
        timeline["days"][1]["events"][0]["id"] = timeline["days"][0]["events"][0]["id"]
        self.assert_invalid(timeline, "id")

    def test_rejects_invalid_events_and_legs(self):
        mutations = [
            ("time", lambda t: t["days"][0]["events"][0].update(time="24:00")),
            ("time", lambda t: t["days"][0]["events"][1].update(time="08:00")),
            ("placeId", lambda t: t["days"][0]["events"][0].update(placeId="missing")),
            ("events", lambda t: t["days"][0].update(events=t["days"][0]["events"][:1])),
            ("legs", lambda t: t["days"][0]["legs"].pop()),
            ("toEventId", lambda t: t["days"][0]["legs"][0].update(toEventId="wrong")),
            ("viaPlaceIds", lambda t: t["days"][0]["legs"][0].update(viaPlaceIds=["missing"])),
            ("modeHint", lambda t: t["days"][0]["legs"][0].update(modeHint="car")),
            ("transportTransactionId", lambda t: t["days"][0]["legs"][0].update(modeHint="bus")),
            ("transportTransactionId", lambda t: t["days"][0]["legs"][0].update(modeHint="train")),
            ("other", lambda t: t["days"][0]["events"][0].update(other=1)),
        ]
        for context, mutate in mutations:
            with self.subTest(context=context, mutate=mutate):
                timeline = self.timeline()
                mutate(timeline)
                self.assert_invalid(timeline, context)

    def test_accepts_optional_fields_without_transaction_lookup(self):
        timeline = self.timeline()
        timeline["days"][0]["legs"][0]["viaPlaceIds"] = ["jrShibuya", "shibuyaMuji"]
        timeline["days"][0]["events"][0]["transactionId"] = "deleted-from-database"
        self.assertEqual(validate_timeline(timeline), timeline)


if __name__ == "__main__":
    unittest.main()
