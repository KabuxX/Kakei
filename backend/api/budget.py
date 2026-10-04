"""Read and replace the shared category budgets."""

from fastapi import FastAPI, Request
from api.http import json_response, read_json
from db.store import Store


def register_budget(app: FastAPI, store: Store) -> None:
    @app.get('/api/budget')
    def get_budget():
        return json_response(200, {'categories': store.get_budget()})

    @app.put('/api/budget')
    async def put_budget(request: Request):
        payload = await read_json(request, 16 * 1024)
        return json_response(200, {'categories': store.update_budget(payload)})
