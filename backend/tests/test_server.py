import http.client
import json
import sqlite3
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from server import create_server


class ServerTests(unittest.TestCase):
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
        self.server = create_server(self.db, self.front, port=0)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self._stop)

    def _stop(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def request(self, method, path, body=None, *, origin=None, host=None, content_type="application/json"):
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=3)
        headers = {"Host": host or f"localhost:{self.port}"}
        if method in ("POST", "DELETE", "PUT"):
            headers["Origin"] = origin or f"http://localhost:{self.port}"
        if body is not None:
            if not isinstance(body, (str, bytes)):
                body = json.dumps(body, ensure_ascii=False)
            if isinstance(body, str):
                body = body.encode("utf-8")
            headers["Content-Type"] = content_type
        connection.request(method, path, body=body, headers=headers)
        response = connection.getresponse()
        raw = response.read()
        content = json.loads(raw) if response.getheader("Content-Type", "").startswith("application/json") and raw else raw
        status = response.status
        connection.close()
        return status, content

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

    def test_invalid_json_and_body_limits(self):
        self.assertEqual(self.request("POST", "/api/initialize", "{broken")[0], 400)
        self.assertEqual(self.request("POST", "/api/initialize", "{}", content_type="text/plain")[0], 400)
        self.assertEqual(self.request("POST", "/api/initialize", {"transactions": []})[0], 201)
        status, error = self.request("POST", "/api/transactions", {"title": "x" * 70000})
        self.assertEqual((status, error["error"]["code"]), (413, "body_too_large"))
        status, error = self.request("POST", "/api/transactions", {"title": ""})
        self.assertEqual((status, error["error"]["field"]), (400, "title"))

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
        with patch.object(self.server.store, "list_transactions", side_effect=sqlite3.OperationalError("db unavailable")):
            status, content = self.request("GET", "/api/transactions")
        self.assertEqual((status, content["error"]["code"]), (500, "database_error"))
        self.assertNotIn("db unavailable", content["error"]["message"])


if __name__ == "__main__":
    unittest.main()
