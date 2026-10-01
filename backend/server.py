"""Serve Kakei's static frontend and local JSON API on one origin."""

import argparse
import json
import mimetypes
import sqlite3
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Optional
from urllib.parse import unquote, urlsplit

from store import AlreadyInitialized, NotInitialized, Store
from validation import ValidationError


class HTTPFailure(Exception):
    def __init__(self, status: int, code: str, message: str):
        self.status = status
        self.code = code
        self.message = message


def create_server(db_path: Path, front_dir: Path, *, port: int = 8765) -> ThreadingHTTPServer:
    store = Store(db_path)
    static_root = Path(front_dir).resolve()

    class Handler(BaseHTTPRequestHandler):
        def _json(self, status: int, value: object) -> None:
            raw = json.dumps(value, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def _empty(self, status: int) -> None:
            self.send_response(status)
            self.send_header("Content-Length", "0")
            self.end_headers()

        def _error(self, status: int, code: str, message: str, field: Optional[str] = None) -> None:
            detail = {"code": code, "message": message}
            if field is not None:
                detail["field"] = field
            self._json(status, {"error": detail})

        def _check_origin(self, write: bool) -> None:
            host = self.headers.get("Host", "")
            allowed = {f"localhost:{self.server.server_port}",
                       f"127.0.0.1:{self.server.server_port}"}
            if host not in allowed:
                raise HTTPFailure(403, "forbidden_origin", "ローカルのアドレスからアクセスしてください。")
            if write and self.headers.get("Origin") != f"http://{host}":
                raise HTTPFailure(403, "forbidden_origin", "同じアドレスの画面から操作してください。")

        def _read_json(self, limit: int) -> object:
            content_type = self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
            if content_type != "application/json":
                raise HTTPFailure(400, "invalid_content_type", "JSONを送信してください。")
            try:
                size = int(self.headers.get("Content-Length", ""))
            except ValueError as error:
                raise HTTPFailure(400, "invalid_body", "本文の長さが不正です。") from error
            if size < 0:
                raise HTTPFailure(400, "invalid_body", "本文の長さが不正です。")
            if size > limit:
                raise HTTPFailure(413, "body_too_large", "送信データが大きすぎます。")
            try:
                return json.loads(self.rfile.read(size).decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                raise HTTPFailure(400, "invalid_json", "JSONの形式が正しくありません。") from error

        def _transaction_id(self, path: str) -> str:
            encoded = path[len("/api/transactions/"):]
            try:
                transaction_id = unquote(encoded, errors="strict")
            except UnicodeDecodeError as error:
                raise HTTPFailure(400, "invalid_id", "取引IDが正しくありません。") from error
            if not transaction_id:
                raise HTTPFailure(404, "not_found", "取引が見つかりません。")
            return transaction_id

        def _serve_static(self, path: str) -> None:
            try:
                decoded = unquote(path, errors="strict")
            except UnicodeDecodeError as error:
                raise HTTPFailure(400, "invalid_path", "パスが正しくありません。") from error
            requested = (static_root / decoded.lstrip("/")).resolve()
            if decoded == "/":
                requested = static_root / "index.html"
            try:
                requested.relative_to(static_root)
            except ValueError as error:
                raise HTTPFailure(404, "not_found", "ファイルが見つかりません。") from error
            if not requested.is_file():
                raise HTTPFailure(404, "not_found", "ファイルが見つかりません。")
            raw = requested.read_bytes()
            mime = mimetypes.guess_type(requested.name)[0] or "application/octet-stream"
            self.send_response(200)
            self.send_header("Content-Type", f"{mime}; charset=utf-8" if mime.startswith("text/") or mime == "application/javascript" else mime)
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def _route(self, method: str) -> None:
            path = urlsplit(self.path).path
            self._check_origin(method in ("POST", "DELETE", "PUT", "PATCH"))
            if path.startswith("/api/") and path not in ("/api/status", "/api/initialize") and not store.is_initialized():
                raise NotInitialized()
            if path == "/api/status" and method == "GET":
                self._json(200, {"initialized": store.is_initialized()})
            elif path == "/api/initialize" and method == "POST":
                payload = self._read_json(8 * 1024 * 1024)
                if not isinstance(payload, dict):
                    raise ValidationError("transactions", "取引の配列を指定してください。")
                self._json(201, {"count": store.initialize(payload.get("transactions"))})
            elif path == "/api/transactions" and method == "GET":
                self._json(200, {"transactions": store.list_transactions()})
            elif path == "/api/transactions" and method == "POST":
                self._json(201, {"transaction": store.create_transaction(self._read_json(64 * 1024))})
            elif path == "/api/samples" and method == "DELETE":
                self._json(200, {"deletedCount": store.delete_samples()})
            elif path.startswith("/api/transactions/") and method == "GET":
                item = store.get_transaction(self._transaction_id(path))
                if item is None:
                    raise HTTPFailure(404, "not_found", "取引が見つかりません。")
                self._json(200, {"transaction": item})
            elif path.startswith("/api/transactions/") and method == "DELETE":
                if not store.delete_transaction(self._transaction_id(path)):
                    raise HTTPFailure(404, "not_found", "取引が見つかりません。")
                self._empty(204)
            elif path.startswith("/api/"):
                if path in ("/api/status", "/api/initialize", "/api/transactions", "/api/samples") or path.startswith("/api/transactions/"):
                    raise HTTPFailure(405, "method_not_allowed", "この操作は利用できません。")
                raise HTTPFailure(404, "not_found", "APIが見つかりません。")
            elif method == "GET":
                self._serve_static(path)
            else:
                raise HTTPFailure(405, "method_not_allowed", "この操作は利用できません。")

        def _handle(self, method: str) -> None:
            try:
                self._route(method)
            except HTTPFailure as error:
                self._error(error.status, error.code, error.message)
            except ValidationError as error:
                self._error(400, "validation_error", error.message, error.field)
            except AlreadyInitialized:
                self._error(409, "already_initialized", "取引は既に初期化されています。")
            except NotInitialized:
                self._error(409, "not_initialized", "取引の初期化が必要です。")
            except sqlite3.Error:
                self._error(500, "database_error", "データベースにアクセスできませんでした。")

        def do_GET(self) -> None:
            self._handle("GET")

        def do_POST(self) -> None:
            self._handle("POST")

        def do_DELETE(self) -> None:
            self._handle("DELETE")

        def do_PUT(self) -> None:
            self._handle("PUT")

        def do_PATCH(self) -> None:
            self._handle("PATCH")

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.daemon_threads = True
    server.store = store
    return server


def main(argv: Optional[list] = None) -> int:
    root = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description="Run Kakei's local backend and frontend")
    parser.add_argument("--db", type=Path, default=root / "data" / "kakei.sqlite3",
                        help="SQLite database path (default: backend/data/kakei.sqlite3)")
    args = parser.parse_args(argv)
    server = create_server(args.db, root.parent / "front")
    print("Kakei: http://localhost:8765/", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
