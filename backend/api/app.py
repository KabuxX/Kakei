"""Application wiring, local access control, and static serving."""

import sqlite3
import os
import asyncio
from contextlib import asynccontextmanager, suppress
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles

from api.http import HTTPFailure, error_response, json_response
from api.transactions import register_transactions
from api.transaction_addresses import register_transaction_addresses
from api.agent import register_agent
from api.receipts import register_receipts
from config.paths import TIMELINE_PATH
from db.store import AlreadyInitialized, NotInitialized, Store, TrajectoryConflict, TrajectoryNotFound
from services.trajectory_validation import load_timeline
from services.validation import ValidationError


def create_app(db_path: Path, front_dir: Path, *, port: int = 8765,
               timeline_path: Path = TIMELINE_PATH, runner_factory=None) -> FastAPI:
    """Build an app with an isolated store for tests or local execution."""
    store = Store(db_path)
    store.seed_trajectory_once(lambda: load_timeline(timeline_path))
    @asynccontextmanager
    async def lifespan(app):
        async def cleanup():
            import time
            from db.google_place_cache import purge_expired_coordinates
            while True:
                await asyncio.sleep(60)
                with store._connection() as connection:
                    purge_expired_coordinates(connection,time.time())
        task=asyncio.create_task(cleanup())
        try:
            yield
        finally:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
    app = FastAPI(lifespan=lifespan)
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
        if (path.startswith("/api/") and path not in ("/api/status", "/api/initialize", "/api/trajectory", "/api/agent/status", "/api/map-config")
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

    @app.exception_handler(TrajectoryNotFound)
    async def handle_trajectory_not_found(_request: Request, error: TrajectoryNotFound):
        return error_response(404, "not_found", str(error))

    @app.exception_handler(TrajectoryConflict)
    async def handle_trajectory_conflict(_request: Request, error: TrajectoryConflict):
        return error_response(409, "conflict", str(error))

    @app.exception_handler(sqlite3.Error)
    async def handle_database_error(_request: Request, _error_value: sqlite3.Error):
        return error_response(500, "database_error", "データベースにアクセスできませんでした。")

    register_receipts(app, store)
    register_agent(app, store, runner_factory)
    register_transactions(app, store)
    register_transaction_addresses(app, store)
    from api.google_places import register_google_places
    register_google_places(app)

    @app.get("/api/map-config")
    def map_config():
        key=os.getenv('GOOGLE_MAPS_BROWSER_API_KEY','').strip()
        if key and key==os.getenv('GOOGLE_PLACES_API_KEY','').strip():
            key=''
        return json_response(200, {'googleMapsBrowserKey':key or None,'googleMapId':os.getenv('GOOGLE_MAPS_MAP_ID','').strip() or 'DEMO_MAP_ID'})

    @app.api_route("/api/{remaining:path}", methods=["GET", "POST", "DELETE", "PUT", "PATCH", "OPTIONS", "HEAD"])
    def unknown_api(request: Request, remaining: str):
        path = request.url.path
        if (path in ("/api/status", "/api/initialize", "/api/transactions", "/api/samples", "/api/trajectory", "/api/map-config")
                or path.startswith(("/api/transactions/", "/api/trajectory/"))):
            raise HTTPFailure(405, "method_not_allowed", "この操作は利用できません。")
        raise HTTPFailure(404, "not_found", "APIが見つかりません。")

    app.mount("/", StaticFiles(directory=str(front_dir), html=True), name="front")
    return app
