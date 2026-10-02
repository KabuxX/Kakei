"""Application wiring, local access control, and static serving."""

import sqlite3
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles

from api.http import HTTPFailure, error_response
from api.transactions import register_transactions
from config.paths import TIMELINE_PATH
from db.store import AlreadyInitialized, NotInitialized, Store
from services.trajectory_validation import load_timeline
from services.validation import ValidationError


def create_app(db_path: Path, front_dir: Path, *, port: int = 8765,
               timeline_path: Path = TIMELINE_PATH) -> FastAPI:
    """Build an app with an isolated store for tests or local execution."""
    store = Store(db_path)
    store.sync_trajectory(load_timeline(timeline_path))
    app = FastAPI()
    app.state.store = store

    @app.middleware("http")
    async def local_access(request: Request, call_next):
        host = request.headers.get("host", "")
        allowed = {f"localhost:{port}", f"127.0.0.1:{port}"}
        if host not in allowed:
            return error_response(403, "forbidden_origin", "ローカルのアドレスからアクセスしてください。")
        if request.method in ("POST", "DELETE", "PUT", "PATCH"):
            if request.headers.get("origin") != f"http://{host}":
                return error_response(403, "forbidden_origin", "同じアドレスの画面から操作してください。")
        path = request.url.path
        if (path.startswith("/api/") and path not in ("/api/status", "/api/initialize")
                and not path.startswith("/api/trajectory/")):
            try:
                if not store.is_initialized():
                    return error_response(409, "not_initialized", "取引の初期化が必要です。")
            except sqlite3.Error:
                return error_response(500, "database_error", "データベースにアクセスできませんでした。")
        return await call_next(request)

    @app.exception_handler(HTTPFailure)
    async def handle_http_failure(_request: Request, error: HTTPFailure):
        return error_response(error.status, error.code, error.message)

    @app.exception_handler(ValidationError)
    async def handle_validation_error(_request: Request, error: ValidationError):
        return error_response(400, "validation_error", error.message, error.field)

    @app.exception_handler(AlreadyInitialized)
    async def handle_already_initialized(_request: Request, _error_value: AlreadyInitialized):
        return error_response(409, "already_initialized", "取引は既に初期化されています。")

    @app.exception_handler(NotInitialized)
    async def handle_not_initialized(_request: Request, _error_value: NotInitialized):
        return error_response(409, "not_initialized", "取引の初期化が必要です。")

    @app.exception_handler(sqlite3.Error)
    async def handle_database_error(_request: Request, _error_value: sqlite3.Error):
        return error_response(500, "database_error", "データベースにアクセスできませんでした。")

    register_transactions(app, store)

    @app.api_route("/api/{remaining:path}", methods=["GET", "POST", "DELETE", "PUT", "PATCH", "OPTIONS", "HEAD"])
    def unknown_api(request: Request, remaining: str):
        path = request.url.path
        if (path in ("/api/status", "/api/initialize", "/api/transactions", "/api/samples")
                or path.startswith(("/api/transactions/", "/api/trajectory/"))):
            raise HTTPFailure(405, "method_not_allowed", "この操作は利用できません。")
        raise HTTPFailure(404, "not_found", "APIが見つかりません。")

    app.mount("/", StaticFiles(directory=str(front_dir), html=True), name="front")
    return app
