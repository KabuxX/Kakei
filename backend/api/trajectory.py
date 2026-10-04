"""Day trajectory HTTP route."""

import re
from datetime import date as calendar_date

from fastapi import FastAPI, Request
from fastapi.responses import Response

from api.http import HTTPFailure, json_response, read_json
from db.store import Store
from services.trajectory_mutation import parse_trajectory_command


def register_trajectory(app: FastAPI, store: Store) -> None:
    @app.get("/api/trajectory")
    def trajectory_dates():
        return json_response(200, {"dates": store.list_trajectory_dates()})

    async def mutate(request: Request, action: str, status: int):
        payload = await read_json(request, 1024 * 1024)
        command = parse_trajectory_command(payload, request.method)
        result = store.mutate_trajectory(command, action)
        if action == "delete":
            return Response(status_code=204, headers={"Cache-Control": "no-store"})
        return json_response(status, result)

    @app.post("/api/trajectory")
    async def create_trajectory(request: Request):
        return await mutate(request, "create", 201)

    @app.put("/api/trajectory")
    async def update_trajectory(request: Request):
        return await mutate(request, "update", 200)

    @app.delete("/api/trajectory")
    async def delete_trajectory(request: Request):
        return await mutate(request, "delete", 204)

    @app.get("/api/trajectory/{requested_date}")
    async def trajectory_day(requested_date: str):
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", requested_date):
            raise HTTPFailure(400, "invalid_date", "日付は YYYY-MM-DD で指定してください。")
        try:
            calendar_date.fromisoformat(requested_date)
        except ValueError as error:
            raise HTTPFailure(400, "invalid_date", "存在する日付を指定してください。") from error
        payload = store.get_trajectory_day_context(requested_date)
        if payload is None:
            raise HTTPFailure(404, "not_found", "指定日の軌跡が見つかりません。")
        if any(place.get('provider')=='google' for place in payload['places'].values()):
            import time
            from agent.google_places import GooglePlacesClient
            from services.google_place_display import GooglePlaceDisplay
            async with GooglePlacesClient() as client:
                payload=await GooglePlaceDisplay(store,client).hydrate(payload,now=time.time())
        return json_response(200, payload)
