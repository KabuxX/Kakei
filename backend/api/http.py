"""JSON request validation and HTTP responses."""

import json
from typing import Optional

from fastapi import Request
from fastapi.responses import JSONResponse


class HTTPFailure(Exception):
    def __init__(self, status: int, code: str, message: str):
        self.status = status
        self.code = code
        self.message = message


def json_response(status: int, value: object) -> JSONResponse:
    return JSONResponse(value, status_code=status, headers={"Cache-Control": "no-store"})


def error_response(status: int, code: str, message: str, field: Optional[str] = None) -> JSONResponse:
    detail = {"code": code, "message": message}
    if field is not None:
        detail["field"] = field
    return json_response(status, {"error": detail})


async def read_json(request: Request, limit: int) -> object:
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
