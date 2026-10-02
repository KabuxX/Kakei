import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.trajectory_mutation import parse_trajectory_command
from services.validation import ValidationError


class TrajectoryMutationCommandTests(unittest.TestCase):
    def test_parse_each_kind(self):
        cases = (
            ({"kind": "day", "date": "2026-10-03", "data": {"events": [], "legs": []}}, "day", "2026-10-03", None),
            ({"kind": "event", "date": "2026-10-03", "id": "visit-1", "data": {"time": "09:00", "placeId": "p"}}, "event", "2026-10-03", "visit-1"),
            ({"kind": "leg", "date": "2026-10-03", "fromEventId": "visit-1", "toEventId": "visit-2", "data": {}}, "leg", "2026-10-03", None),
            ({"kind": "place", "id": "p", "data": {"name": "店", "address": "東京", "coordinates": [139.7, 35.6], "sourceUrl": "https://example.com"}}, "place", None, "p"),
        )
        for payload, kind, date, id_value in cases:
            with self.subTest(kind=kind):
                command = parse_trajectory_command(payload, "POST")
                self.assertEqual((command.kind, command.date, command.id), (kind, date, id_value))
                self.assertEqual(command.data, payload["data"])

    def test_reject_unknown_and_wrong_data(self):
        invalid = (
            {"kind": [], "id": "p", "data": {}},
            {"kind": "place", "id": "p", "data": []},
            {"kind": "place", "id": "p", "data": {}, "extra": 1},
            {"kind": "event", "date": "2026-10-03", "id": "e"},
            {"kind": "day", "date": "2026-02-30", "data": {"events": [], "legs": []}},
            {"kind": "leg", "date": "2026-10-03", "fromEventId": "x", "toEventId": "x", "data": {}},
        )
        for payload in invalid:
            with self.subTest(payload=payload), self.assertRaises(ValidationError):
                parse_trajectory_command(payload, "POST")
        with self.assertRaises(ValidationError):
            parse_trajectory_command({"kind": "place", "id": "p", "data": {}}, "DELETE")

    def test_put_retains_optional_field_omission(self):
        payload = {"kind": "event", "date": "2026-10-03", "id": "e", "data": {"time": "09:00", "placeId": "p"}}
        command = parse_trajectory_command(payload, "PUT")
        self.assertEqual(command.data, {"time": "09:00", "placeId": "p"})
        self.assertNotIn("transactionId", command.data)


if __name__ == "__main__":
    unittest.main()
