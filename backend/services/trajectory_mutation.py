"""Parse the shared create, update, and delete trajectory command envelope."""

import re
from dataclasses import dataclass
from datetime import date as calendar_date

from services.validation import ValidationError


@dataclass(frozen=True)
class TrajectoryCommand:
    kind: str
    date: str | None
    id: str | None
    from_event_id: str | None
    to_event_id: str | None
    data: dict | None


_IDENTITY = {
    "day": {"date"},
    "event": {"date", "id"},
    "leg": {"date", "fromEventId", "toEventId"},
    "place": {"id"},
}

_DATA_FIELDS = {
    "day": ({"events", "legs"}, set()),
    "event": ({"time", "placeId"}, {"transactionId", "timeEvidence", "timeEvidenceNote"}),
    "leg": (set(), {"modeHint", "transportTransactionId", "viaPlaceIds", "modeEvidence", "modeEvidenceNote"}),
    "place": ({"name", "address", "coordinates", "sourceUrl"}, {"placeEvidence", "attribution"}),
}


def _invalid(message: str) -> None:
    raise ValidationError("trajectory", message)


def _date(value: object) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        _invalid("日付は YYYY-MM-DD で指定してください。")
    try:
        calendar_date.fromisoformat(value)
    except ValueError:
        _invalid("存在する日付を指定してください。")
    return value


def _id(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        _invalid("IDは空でない文字列で指定してください。")
    return value


def parse_trajectory_command(payload: object, method: str) -> TrajectoryCommand:
    if method not in {"POST", "PUT", "DELETE"} or not isinstance(payload, dict):
        _invalid("軌跡の操作をJSONオブジェクトで指定してください。")
    kind = payload.get("kind")
    if not isinstance(kind, str) or kind not in _IDENTITY:
        _invalid("kind は day、event、leg、place のいずれかを指定してください。")
    expected = {"kind", *_IDENTITY[kind]}
    if method != "DELETE":
        expected.add("data")
    if payload.keys() != expected:
        _invalid("軌跡の操作に必要な項目だけを指定してください。")

    date = _date(payload["date"]) if "date" in payload else None
    id_value = _id(payload["id"]) if "id" in payload else None
    from_event_id = _id(payload["fromEventId"]) if "fromEventId" in payload else None
    to_event_id = _id(payload["toEventId"]) if "toEventId" in payload else None
    if from_event_id is not None and from_event_id == to_event_id:
        _invalid("区間の両端には異なるイベントを指定してください。")

    data = payload.get("data")
    if method != "DELETE":
        if not isinstance(data, dict):
            _invalid("data はJSONオブジェクトで指定してください。")
        required, optional = _DATA_FIELDS[kind]
        if required - data.keys() or data.keys() - required - optional:
            _invalid("data の項目が正しくありません。")
        if kind == "day" and (not isinstance(data["events"], list) or not isinstance(data["legs"], list)):
            _invalid("events と legs は配列で指定してください。")
    return TrajectoryCommand(kind, date, id_value, from_event_id, to_event_id, data)
