"""Serve Kakei's frontend and local JSON API with FastAPI."""

import json
import os
import re
import sqlite3
from datetime import date as calendar_date
from pathlib import Path
from typing import Optional

from runtime import require_supported_python

require_supported_python()

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from store import AlreadyInitialized, NotInitialized, Store
from validation import ValidationError

_timeline_path = Path(__file__).resolve().parent.parent / "front" / "src" / "data" / "september-timeline.json"


class HTTPFailure(Exception):
    def __init__(self, status: int, code: str, message: str):
        self.status = status
        self.code = code
        self.message = message


def _json(status: int, value: object) -> JSONResponse:
    return JSONResponse(value, status_code=status, headers={"Cache-Control": "no-store"})


def _error(status: int, code: str, message: str, field: Optional[str] = None) -> JSONResponse:
    detail = {"code": code, "message": message}
    if field is not None:
        detail["field"] = field
    return _json(status, {"error": detail})


async def _read_json(request: Request, limit: int) -> object:
    content_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if content_type != "application/json":
        raise HTTPFailure(400, "invalid_content_type", "JSONを送信してください。")
    try:
        declared_size = int(request.headers.get("content-length", ""))
    except ValueError as error:
        raise HTTPFailure(400, "invalid_body", "本文の長さが不正です。") from error
    if declared_size < 0:
        raise HTTPFailure(400, "invalid_body", "本文の長さが不正です。")
    if declared_size > limit:
        raise HTTPFailure(413, "body_too_large", "送信データが大きすぎます。")
    chunks = []
    size = 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > limit:
            raise HTTPFailure(413, "body_too_large", "送信データが大きすぎます。")
        chunks.append(chunk)
    try:
        return json.loads(b"".join(chunks).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise HTTPFailure(400, "invalid_json", "JSONの形式が正しくありません。") from error


def create_app(db_path: Path, front_dir: Path, *, port: int = 8765) -> FastAPI:
    """Build an app with an isolated store for tests or local execution."""
    store = Store(db_path)
    timeline = json.loads(_timeline_path.read_text(encoding="utf-8"))
    app = FastAPI()
    app.state.store = store

    @app.middleware("http")
    async def local_access(request: Request, call_next):
        host = request.headers.get("host", "")
        allowed = {f"localhost:{port}", f"127.0.0.1:{port}"}
        if host not in allowed:
            return _error(403, "forbidden_origin", "ローカルのアドレスからアクセスしてください。")
        if request.method in ("POST", "DELETE", "PUT", "PATCH"):
            if request.headers.get("origin") != f"http://{host}":
                return _error(403, "forbidden_origin", "同じアドレスの画面から操作してください。")
        path = request.url.path
        if (path.startswith("/api/") and path not in ("/api/status", "/api/initialize")
                and not path.startswith("/api/trajectory/")):
            try:
                if not store.is_initialized():
                    return _error(409, "not_initialized", "取引の初期化が必要です。")
            except sqlite3.Error:
                return _error(500, "database_error", "データベースにアクセスできませんでした。")
        return await call_next(request)

    @app.exception_handler(HTTPFailure)
    async def handle_http_failure(_request: Request, error: HTTPFailure):
        return _error(error.status, error.code, error.message)

    @app.exception_handler(ValidationError)
    async def handle_validation_error(_request: Request, error: ValidationError):
        return _error(400, "validation_error", error.message, error.field)

    @app.exception_handler(AlreadyInitialized)
    async def handle_already_initialized(_request: Request, _error_value: AlreadyInitialized):
        return _error(409, "already_initialized", "取引は既に初期化されています。")

    @app.exception_handler(NotInitialized)
    async def handle_not_initialized(_request: Request, _error_value: NotInitialized):
        return _error(409, "not_initialized", "取引の初期化が必要です。")

    @app.exception_handler(sqlite3.Error)
    async def handle_database_error(_request: Request, _error_value: sqlite3.Error):
        return _error(500, "database_error", "データベースにアクセスできませんでした。")

    @app.get("/api/status")
    def status():
        return _json(200, {"initialized": store.is_initialized()})

    @app.post("/api/initialize")
    async def initialize(request: Request):
        payload = await _read_json(request, 8 * 1024 * 1024)
        if not isinstance(payload, dict):
            raise ValidationError("transactions", "取引の配列を指定してください。")
        return _json(201, {"count": store.initialize(payload.get("transactions"))})

    @app.get("/api/transactions")
    def transactions():
        return _json(200, {"transactions": store.list_transactions()})

    @app.get("/api/trajectory/{requested_date}")
    def trajectory_day(requested_date: str):
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", requested_date):
            raise HTTPFailure(400, "invalid_date", "日付は YYYY-MM-DD で指定してください。")
        try:
            calendar_date.fromisoformat(requested_date)
        except ValueError as error:
            raise HTTPFailure(400, "invalid_date", "存在する日付を指定してください。") from error
        day = next((item for item in timeline["days"] if item["date"] == requested_date), None)
        if day is None:
            raise HTTPFailure(404, "not_found", "指定日の軌跡サンプルが見つかりません。")
        place_ids = {event["placeId"] for event in day["events"]}
        place_ids.update(place_id for leg in day["legs"] for place_id in leg.get("viaPlaceIds", []))
        places = {place_id: place for place_id, place in timeline["places"].items() if place_id in place_ids}
        return _json(200, {"places": places, "days": [day]})

    @app.post("/api/transactions")
    async def create_transaction(request: Request):
        draft = await _read_json(request, 64 * 1024)
        return _json(201, {"transaction": store.create_transaction(draft)})

    @app.delete("/api/samples")
    def delete_samples():
        return _json(200, {"deletedCount": store.delete_samples()})

    @app.get("/api/transactions/{transaction_id:path}")
    def transaction(transaction_id: str):
        item = store.get_transaction(transaction_id)
        if item is None:
            raise HTTPFailure(404, "not_found", "取引が見つかりません。")
        return _json(200, {"transaction": item})

    @app.delete("/api/transactions/{transaction_id:path}")
    def delete_transaction(transaction_id: str):
        if not store.delete_transaction(transaction_id):
            raise HTTPFailure(404, "not_found", "取引が見つかりません。")
        return Response(status_code=204)

    @app.api_route("/api/{remaining:path}", methods=["GET", "POST", "DELETE", "PUT", "PATCH", "OPTIONS", "HEAD"])
    def unknown_api(request: Request, remaining: str):
        path = request.url.path
        if (path in ("/api/status", "/api/initialize", "/api/transactions", "/api/samples")
                or path.startswith(("/api/transactions/", "/api/trajectory/"))):
            raise HTTPFailure(405, "method_not_allowed", "この操作は利用できません。")
        raise HTTPFailure(404, "not_found", "APIが見つかりません。")

    app.mount("/", StaticFiles(directory=str(front_dir), html=True), name="front")
    return app


_backend_dir = Path(__file__).resolve().parent
app = create_app(
    Path(os.getenv("KAKEI_DB_PATH") or _backend_dir / "data" / "kakei.sqlite3"),
    _backend_dir.parent / "front" / "dist",
)
