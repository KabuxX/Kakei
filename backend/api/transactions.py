"""Transaction HTTP routes."""

from fastapi import FastAPI, Request
from fastapi.responses import Response

from api.http import HTTPFailure, json_response, read_json
from api.trajectory import register_trajectory
from db.store import Store
from services.validation import ValidationError


def register_transactions(app: FastAPI, store: Store) -> None:
    @app.get("/api/status")
    def status():
        return json_response(200, {"initialized": store.is_initialized()})

    @app.post("/api/initialize")
    async def initialize(request: Request):
        payload = await read_json(request, 8 * 1024 * 1024)
        if not isinstance(payload, dict):
            raise ValidationError("transactions", "取引の配列を指定してください。")
        return json_response(201, {"count": store.initialize(payload.get("transactions"))})

    @app.get("/api/transactions")
    def transactions():
        return json_response(200, {"transactions": store.list_transactions()})

    register_trajectory(app, store)

    @app.post("/api/transactions")
    async def create_transaction(request: Request):
        draft = await read_json(request, 64 * 1024)
        return json_response(201, {"transaction": store.create_transaction(draft)})

    @app.delete("/api/samples")
    def delete_samples():
        return json_response(200, {"deletedCount": store.delete_samples()})

    @app.get("/api/transactions/{transaction_id:path}")
    def transaction(transaction_id: str):
        item = store.get_transaction(transaction_id)
        if item is None:
            raise HTTPFailure(404, "not_found", "取引が見つかりません。")
        return json_response(200, {"transaction": item})

    @app.delete("/api/transactions/{transaction_id:path}")
    def delete_transaction(transaction_id: str):
        if not store.delete_transaction(transaction_id):
            raise HTTPFailure(404, "not_found", "取引が見つかりません。")
        return Response(status_code=204)
