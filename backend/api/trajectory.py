"""Day trajectory HTTP route."""

import re
from datetime import date as calendar_date

from fastapi import FastAPI

from api.http import HTTPFailure, json_response
from db.store import Store


def register_trajectory(app: FastAPI, store: Store) -> None:
    @app.get("/api/trajectory/{requested_date}")
    def trajectory_day(requested_date: str):
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", requested_date):
            raise HTTPFailure(400, "invalid_date", "日付は YYYY-MM-DD で指定してください。")
        try:
            calendar_date.fromisoformat(requested_date)
        except ValueError as error:
            raise HTTPFailure(400, "invalid_date", "存在する日付を指定してください。") from error
        payload = store.get_trajectory_day(requested_date)
        if payload is None:
            raise HTTPFailure(404, "not_found", "指定日の軌跡サンプルが見つかりません。")
        return json_response(200, payload)
