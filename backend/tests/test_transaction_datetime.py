import importlib
import importlib.util
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

if importlib.util.find_spec("transaction_datetime") is None:
    transaction_datetime = None
else:
    transaction_datetime = importlib.import_module("transaction_datetime")


class EstimatedDatetimeTests(unittest.TestCase):
    def helper(self, name):
        self.assertIsNotNone(transaction_datetime, "transaction_datetime module is missing")
        function = getattr(transaction_datetime, name, None)
        self.assertTrue(callable(function), f"{name} is missing")
        return function

    def test_single_estimated_record_uses_noon(self):
        assign = self.helper("assign_estimated_datetimes")
        result = assign([{"id": "only", "date": "2026-10-01"}])

        self.assertEqual(result, [{
            "id": "only", "date": "2026-10-01T12:00", "timeEstimated": True,
        }])

    def test_assigns_deterministic_distinct_estimated_minutes(self):
        assign = self.helper("assign_estimated_datetimes")
        records = [
            {"id": "c", "date": "2026-10-01"},
            {"id": "a", "date": "2026-10-01"},
            {"id": "b", "date": "2026-10-01"},
        ]

        result = assign(records)

        self.assertEqual({record["id"]: record["date"] for record in result}, {
            "a": "2026-10-01T11:30",
            "b": "2026-10-01T15:00",
            "c": "2026-10-01T18:30",
        })
        self.assertEqual([record["id"] for record in result], ["c", "a", "b"])
        self.assertTrue(all(record["timeEstimated"] for record in result))
        self.assertEqual(assign(records), result)
        self.assertEqual([record["date"] for record in records], [
            "2026-10-01", "2026-10-01", "2026-10-01",
        ])

    def test_rejects_more_than_1440_same_day_records(self):
        assign = self.helper("assign_estimated_datetimes")
        records = [
            {"id": f"row-{index:04d}", "date": "2026-10-01"}
            for index in range(1441)
        ]

        with self.assertRaises(ValueError):
            assign(records)


if __name__ == "__main__":
    unittest.main()
