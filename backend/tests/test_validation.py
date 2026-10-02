import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.validation import ValidationError, normalize_transaction


class TransactionValidationTests(unittest.TestCase):
    def test_new_income_and_itemized_expense(self):
        income = normalize_transaction({
            "title": " 給与 ", "date": "2026-09-28", "type": "income",
            "category": "収入", "amount": 320000,
        })
        self.assertEqual(income, {
            "title": "給与", "date": "2026-09-28", "type": "income",
            "category": "収入", "amount": 320000,
        })

        expense = normalize_transaction({
            "title": " 買い物 ", "date": "2026-09-27", "type": "expense",
            "category": "食費", "amount": 300, "merchant": " スーパー ",
            "paymentMethod": "cash", "items": [
                {"name": " パン ", "amount": 200},
                {"name": "牛乳", "amount": 100},
            ],
        })
        self.assertEqual(expense, {
            "title": "買い物", "date": "2026-09-27", "type": "expense",
            "category": "食費", "amount": 300, "merchant": "スーパー",
            "paymentMethod": "cash", "items": [
                {"name": "パン", "amount": 200},
                {"name": "牛乳", "amount": 100},
            ],
        })

    def test_invalid_new_fields(self):
        base = {
            "title": "買い物", "date": "2026-09-27", "type": "expense",
            "category": "食費", "amount": 300, "merchant": "スーパー",
            "paymentMethod": "cash", "items": [],
        }
        cases = [
            ({"title": "   "}, "title"),
            ({"title": "あ" * 61}, "title"),
            ({"date": "2026-02-30"}, "date"),
            ({"amount": 0}, "amount"),
            ({"amount": 1.5}, "amount"),
            ({"amount": True}, "amount"),
            ({"category": "交際費"}, "category"),
            ({"paymentMethod": "bitcoin"}, "paymentMethod"),
            ({"paymentMethod": []}, "paymentMethod"),
            ({"items": [{"name": "パン", "amount": 200}]}, "items"),
            ({"id": "user-supplied"}, "id"),
        ]
        for change, field in cases:
            with self.subTest(change=change):
                with self.assertRaises(ValidationError) as raised:
                    normalize_transaction({**base, **change})
                self.assertEqual(raised.exception.field, field)

    def test_legacy_import(self):
        old = normalize_transaction({
            "id": "old-1", "title": "古い支出", "date": "2026-08-01",
            "type": "expense", "category": "旧カテゴリ", "amount": 500,
        }, import_mode=True)
        self.assertEqual(old["category"], "旧カテゴリ")
        self.assertIsNone(old["merchant"])
        self.assertIsNone(old["paymentMethod"])
        self.assertEqual(old["items"], [])

        partial = normalize_transaction({
            "id": "old-2", "title": "買い物", "date": "2026-08-02",
            "type": "expense", "category": "食費", "amount": 500,
            "merchant": " 店 ", "paymentMethod": [],
            "items": [{"name": "パン", "amount": 300}],
        }, import_mode=True)
        self.assertEqual(partial["merchant"], "店")
        self.assertIsNone(partial["paymentMethod"])
        self.assertEqual(partial["items"], [])


if __name__ == "__main__":
    unittest.main()
