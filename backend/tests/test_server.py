import json
import copy
import os
import re
import runpy
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from contextlib import closing
from unittest.mock import patch
from urllib.parse import quote

from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import server
from api.app import create_app
from store import Store


TIMELINE_PATH = Path(__file__).resolve().parents[2] / "front" / "src" / "data" / "september-timeline.json"


class ServerTests(unittest.TestCase):
    def test_default_app_serves_built_react_page_and_assets(self):
        with TestClient(server.app) as client:
            response = client.get("/", headers={"Host": "localhost:8765"})
            self.assertEqual(response.status_code, 200)
            self.assertIn('id="root"', response.text)
            assets = re.findall(r'(?:src|href)="(/assets/[^"]+)"', response.text)
            self.assertTrue(any(path.endswith(".js") for path in assets))
            for path in assets:
                asset = client.get(path, headers={"Host": "localhost:8765"})
                self.assertEqual(asset.status_code, 200, path)
            status = client.get("/api/status", headers={"Host": "localhost:8765"})
            self.assertEqual(status.status_code, 200)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.db = root / "kakei.sqlite3"
        self.front = root / "front"
        self.front.mkdir()
        (self.front / "index.html").write_text("<title>Kakei</title>", encoding="utf-8")
        (self.front / "app.js").write_text("const app = true;", encoding="utf-8")
        (root / "secret.txt").write_text("private", encoding="utf-8")
        self.app = server.create_app(self.db, self.front)
        self.client = TestClient(self.app, raise_server_exceptions=False)
        self.addCleanup(self.client.close)

    def request(self, method, path, body=None, *, origin=None, host=None, content_type="application/json"):
        headers = {"Host": host or "localhost:8765"}
        if method in ("POST", "DELETE", "PUT"):
            headers["Origin"] = origin or "http://localhost:8765"
        if body is not None:
            if not isinstance(body, (str, bytes)):
                body = json.dumps(body, ensure_ascii=False)
            if isinstance(body, str):
                body = body.encode("utf-8")
            headers["Content-Type"] = content_type
        response = self.client.request(method, path, content=body, headers=headers)
        content = response.json() if response.headers.get("Content-Type", "").startswith("application/json") and response.content else response.content
        return response.status_code, content

    def test_api_package_factory_preserves_status_and_trajectory_contracts(self):
        app = create_app(Path(self.temp.name) / "package.sqlite3", self.front)
        with TestClient(app) as client:
            headers = {"Host": "localhost:8765"}
            status = client.get("/api/status", headers=headers)
            self.assertEqual((status.status_code, status.json()), (200, {"initialized": False}))
            response = client.get("/api/trajectory/2026-09-29", headers=headers)
            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertEqual(set(payload), {"places", "days"})
            self.assertEqual(len(payload["days"]), 1)
            self.assertEqual(payload["days"][0]["date"], "2026-09-29")
            self.assertEqual(payload["places"]["jrShibuya"]["coordinates"], [139.701636, 35.658034])

    def test_api_lifecycle_and_codes(self):
        self.assertEqual(self.request("GET", "/api/status"), (200, {"initialized": False}))
        status, error = self.request("GET", "/api/transactions")
        self.assertEqual((status, error["error"]["code"]), (409, "not_initialized"))
        status, error = self.request("POST", "/api/transactions", {"title": ""})
        self.assertEqual((status, error["error"]["code"]), (409, "not_initialized"))

        records = [{"id": "sample-0", "title": "給与", "date": "2026-09-01",
                    "type": "income", "category": "収入", "amount": 100}]
        self.assertEqual(self.request("POST", "/api/initialize", {"transactions": records}),
                         (201, {"count": 1}))
        self.assertEqual(self.request("GET", "/api/status"), (200, {"initialized": True}))
        self.assertEqual(self.request("GET", "/api/transactions"), (200, {"transactions": records}))
        self.assertEqual(self.request("GET", "/api/transactions/sample-0"),
                         (200, {"transaction": records[0]}))

        draft = {"title": "買い物", "date": "2026-09-02", "type": "expense",
                 "category": "食費", "amount": 200, "merchant": "店",
                 "paymentMethod": "cash", "items": [{"name": "パン", "amount": 200}]}
        status, result = self.request("POST", "/api/transactions", draft)
        self.assertEqual(status, 201)
        self.assertEqual(result["transaction"]["title"], "買い物")
        self.assertTrue(result["transaction"]["id"])
        self.assertEqual(self.request("DELETE", f'/api/transactions/{result["transaction"]["id"]}'),
                         (204, b""))
        self.assertEqual(self.request("DELETE", "/api/samples"), (200, {"deletedCount": 1}))
        self.assertEqual(self.request("GET", "/api/transactions"), (200, {"transactions": []}))
        self.assertEqual(self.request("POST", "/api/initialize", {"transactions": records})[0], 409)
        self.assertEqual(self.request("PUT", "/api/transactions")[0], 405)
        self.assertEqual(self.request("GET", "/api/unknown")[1]["error"]["code"], "not_found")

    def test_trajectory_day_returns_one_fixed_sample_without_database_initialization(self):
        timeline = json.loads(TIMELINE_PATH.read_text(encoding="utf-8"))
        for source_day in timeline["days"]:
            with self.subTest(date=source_day["date"]):
                day_status, day_payload = self.request("GET", f'/api/trajectory/{source_day["date"]}')
                used_places = {event["placeId"] for event in source_day["events"]}
                used_places.update(place_id for leg in source_day["legs"] for place_id in leg.get("viaPlaceIds", []))
                self.assertEqual(day_status, 200)
                self.assertEqual(day_payload, {
                    "places": {place_id: place for place_id, place in timeline["places"].items() if place_id in used_places},
                    "days": [source_day],
                })
        status, payload = self.request("GET", "/api/trajectory/2026-09-29")
        self.assertEqual(status, 200)
        self.assertEqual(set(payload), {"places", "days"})
        self.assertEqual(len(payload["days"]), 1)
        day = payload["days"][0]
        self.assertEqual(day["date"], "2026-09-29")
        self.assertEqual(day["events"][0], {
            "id": "2026-09-29-1", "time": "08:45", "placeId": "shibuyaStarbucks",
            "transactionId": "sample-20260929-a",
        })
        self.assertEqual(day["legs"][1], {
            "fromEventId": "2026-09-29-2", "toEventId": "2026-09-29-3",
            "modeHint": "train", "transportTransactionId": "sample-20260929-train",
        })
        used_places = {event["placeId"] for event in day["events"]}
        used_places.update(place_id for leg in day["legs"] for place_id in leg.get("viaPlaceIds", []))
        self.assertEqual(set(payload["places"]), used_places)
        self.assertEqual(payload["places"]["jrShibuya"]["coordinates"], [139.701636, 35.658034])
        self.assertEqual(self.request("GET", "/api/status"), (200, {"initialized": False}))

    def test_trajectory_get_reads_sqlite(self):
        with closing(sqlite3.connect(self.db)) as connection:
            updated = connection.execute("""
                UPDATE trajectory_places SET name = 'DB-edited' WHERE id = 'shibuyaStarbucks'
            """)
            self.assertEqual(updated.rowcount, 1)
            connection.commit()
        status, payload = self.request("GET", "/api/trajectory/2026-09-19")
        self.assertEqual(status, 200)
        self.assertEqual(payload["places"]["shibuyaStarbucks"]["name"], "DB-edited")

    def test_trajectory_database_error_response(self):
        with patch.object(self.app.state.store, "get_trajectory_day", side_effect=sqlite3.OperationalError("private details")):
            status, payload = self.request("GET", "/api/trajectory/2026-09-19")
        self.assertEqual((status, payload["error"]["code"]), (500, "database_error"))
        self.assertNotIn("private details", payload["error"]["message"])

    def test_app_creation_resyncs_changed_fixture(self):
        timeline = json.loads(TIMELINE_PATH.read_text(encoding="utf-8"))
        fixture_path = Path(self.temp.name) / "timeline.json"
        first = {"places": timeline["places"], "days": [timeline["days"][0], timeline["days"][-2]]}
        fixture_path.write_text(json.dumps(first, ensure_ascii=False), encoding="utf-8")
        app = server.create_app(self.db, self.front, timeline_path=fixture_path)
        with TestClient(app) as client:
            self.assertEqual(client.get("/api/trajectory/2026-09-29", headers={"Host": "localhost:8765"}).status_code, 200)

        second = copy.deepcopy(first)
        second["days"] = second["days"][:1]
        second["places"]["shibuyaStarbucks"]["name"] = "再同期後の店舗"
        fixture_path.write_text(json.dumps(second, ensure_ascii=False), encoding="utf-8")
        updated_app = server.create_app(self.db, self.front, timeline_path=fixture_path)
        with TestClient(updated_app) as client:
            response = client.get("/api/trajectory/2026-09-19", headers={"Host": "localhost:8765"})
            self.assertEqual(response.json()["places"]["shibuyaStarbucks"]["name"], "再同期後の店舗")
            self.assertEqual(client.get("/api/trajectory/2026-09-29", headers={"Host": "localhost:8765"}).status_code, 404)

    def test_invalid_fixture_fails_startup_without_erasing_saved_rows(self):
        timeline = json.loads(TIMELINE_PATH.read_text(encoding="utf-8"))
        fixture_path = Path(self.temp.name) / "timeline.json"
        fixture_path.write_text(json.dumps({"places": timeline["places"], "days": timeline["days"][:1]}, ensure_ascii=False), encoding="utf-8")
        server.create_app(self.db, self.front, timeline_path=fixture_path)
        previous = Store(self.db).get_trajectory_day("2026-09-19")
        fixture_path.write_text("{broken", encoding="utf-8")

        with self.assertRaises(ValueError):
            server.create_app(self.db, self.front, timeline_path=fixture_path)
        self.assertEqual(Store(self.db).get_trajectory_day("2026-09-19"), previous)

    def test_trajectory_day_rejects_invalid_and_missing_dates(self):
        for date in ("2026-9-02", "2026-09-31"):
            with self.subTest(date=date):
                status, payload = self.request("GET", f"/api/trajectory/{date}")
                self.assertEqual((status, payload["error"]["code"]), (400, "invalid_date"))
        status, payload = self.request("GET", "/api/trajectory/2026-09-02")
        self.assertEqual((status, payload["error"]["code"]), (404, "not_found"))
        status, payload = self.request("POST", "/api/trajectory/2026-09-02")
        self.assertEqual((status, payload["error"]["code"]), (405, "method_not_allowed"))

    def test_ordered_items_api_round_trip(self):
        items = [{"name": "パン", "amount": 100}, {"name": "パン", "amount": 100}]
        record = {"id": "old-expense", "title": "買い物", "date": "2026-09-01",
                  "type": "expense", "category": "食費", "amount": 200,
                  "merchant": "店", "paymentMethod": "cash", "items": items}
        self.assertEqual(self.request("POST", "/api/initialize", {"transactions": [record]}),
                         (201, {"count": 1}))
        list_record = self.request("GET", "/api/transactions")[1]["transactions"][0]
        detail_record = self.request("GET", "/api/transactions/old-expense")[1]["transaction"]
        self.assertEqual(list_record, record)
        self.assertEqual(detail_record, record)

        draft = {key: value for key, value in record.items() if key != "id"}
        status, result = self.request("POST", "/api/transactions", draft)
        self.assertEqual(status, 201)
        created_record = result["transaction"]
        self.assertEqual(created_record["items"], items)
        reloaded_record = self.request("GET", f'/api/transactions/{created_record["id"]}')[1]["transaction"]
        self.assertEqual(reloaded_record, created_record)
        with sqlite3.connect(self.db) as connection:
            columns = {row[1] for row in connection.execute("PRAGMA table_info(transactions)")}
            child_count = connection.execute("SELECT COUNT(*) FROM transaction_items").fetchone()[0]
        self.assertNotIn("items_json", columns)
        self.assertEqual(child_count, 4)

    def test_invalid_json_and_body_limits(self):
        self.assertEqual(self.request("POST", "/api/initialize", "{broken")[0], 400)
        self.assertEqual(self.request("POST", "/api/initialize", "{}", content_type="text/plain")[0], 400)
        self.assertEqual(self.request("POST", "/api/initialize", {"transactions": []})[0], 201)
        status, error = self.request("POST", "/api/transactions", {"title": "x" * 70000})
        self.assertEqual((status, error["error"]["code"]), (413, "body_too_large"))
        status, error = self.request("POST", "/api/transactions", {"title": ""})
        self.assertEqual((status, error["error"]["code"], error["error"]["field"]),
                         (400, "validation_error", "title"))

    def test_cross_origin_write_and_static_escape_rejected(self):
        status, _ = self.request("POST", "/api/initialize", {"transactions": []},
                                 origin="https://example.com")
        self.assertEqual(status, 403)
        status, _ = self.request("POST", "/api/initialize", {"transactions": []},
                                 host="example.com")
        self.assertEqual(status, 403)
        self.assertEqual(self.request("GET", "/")[1], b"<title>Kakei</title>")
        self.assertEqual(self.request("GET", "/app.js")[1], b"const app = true;")
        self.assertNotEqual(self.request("GET", "/%2e%2e/secret.txt")[0], 200)

    def test_encoded_id_and_missing_delete(self):
        unusual_id = "a/b +日本語"
        record = {"id": unusual_id, "title": "給与", "date": "2026-09-01",
                  "type": "income", "category": "収入", "amount": 100}
        self.request("POST", "/api/initialize", {"transactions": [record]})
        path = "/api/transactions/" + quote(unusual_id, safe="")
        self.assertEqual(self.request("GET", path), (200, {"transaction": record}))
        self.assertEqual(self.request("DELETE", "/api/transactions/missing")[0], 404)
        self.assertEqual(self.request("GET", "/api/transactions")[1]["transactions"], [record])
        self.assertEqual(self.request("DELETE", path), (204, b""))

    def test_database_error_response(self):
        self.request("POST", "/api/initialize", {"transactions": []})
        with patch.object(self.app.state.store, "list_transactions", side_effect=sqlite3.OperationalError("db unavailable")):
            status, content = self.request("GET", "/api/transactions")
        self.assertEqual((status, content["error"]["code"]), (500, "database_error"))
        self.assertNotIn("db unavailable", content["error"]["message"])

    def test_cli_entrypoint_uses_configured_database(self):
        with patch.dict(os.environ, {"KAKEI_DB_PATH": str(self.db)}):
            module = runpy.run_path(str(Path(server.__file__)), run_name="kakei_cli_test")
        self.assertIsInstance(module.get("app"), FastAPI)
        with TestClient(module["app"]) as client:
            response = client.post(
                "/api/initialize", json={"transactions": []},
                headers={"Host": "localhost:8765", "Origin": "http://localhost:8765"},
            )
        self.assertEqual(response.status_code, 201)
        self.assertTrue(self.db.is_file())


if __name__ == "__main__":
    unittest.main()
