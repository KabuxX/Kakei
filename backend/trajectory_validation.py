"""Load and validate the fixed trajectory timeline before SQLite sync."""

import json
import math
import re
from datetime import date as calendar_date
from pathlib import Path


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_constant(value):
    raise ValueError(f"Invalid JSON number: {value}")


def _shape(value, required, optional, path):
    if not isinstance(value, dict):
        raise ValueError(f"{path}: object required")
    missing = required - value.keys()
    if missing:
        raise ValueError(f"{path}: missing {sorted(missing)[0]}")
    unknown = value.keys() - required - optional
    if unknown:
        raise ValueError(f"{path}: unknown {sorted(unknown)[0]}")


def _string(value, path):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{path}: nonempty string required")


def _date(value, path):
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ValueError(f"{path}: invalid date")
    try:
        calendar_date.fromisoformat(value)
    except ValueError as error:
        raise ValueError(f"{path}: invalid date") from error


def _time(value, path):
    if not isinstance(value, str) or not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", value):
        raise ValueError(f"{path}: invalid time")


def load_timeline(path: Path) -> dict:
    """Read strict JSON and return the validated, unmodified timeline."""
    try:
        with Path(path).open(encoding="utf-8") as source:
            timeline = json.load(source, object_pairs_hook=_unique_object, parse_constant=_reject_constant)
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError(f"timeline file {path}: {error}") from error
    return validate_timeline(timeline)


def validate_timeline(value: object) -> dict:
    """Check the timeline's shape and cross references without changing it."""
    _shape(value, {"places", "days"}, set(), "timeline")
    places = value["places"]
    days = value["days"]
    if not isinstance(places, dict):
        raise ValueError("places: object required")
    if not isinstance(days, list):
        raise ValueError("days: array required")

    for place_id, place in places.items():
        _string(place_id, "placeId")
        path = f"places.{place_id}"
        _shape(place, {"name", "address", "coordinates", "sourceUrl"}, set(), path)
        _string(place["name"], f"{path}.name")
        _string(place["address"], f"{path}.address")
        source_url = place["sourceUrl"]
        if not isinstance(source_url, str) or not re.fullmatch(r"https://[^/\s]+(?:/[^\s]*)?", source_url):
            raise ValueError(f"{path}.sourceUrl: HTTPS URL required")
        coordinates = place["coordinates"]
        if not isinstance(coordinates, list) or len(coordinates) != 2:
            raise ValueError(f"{path}.coordinates: [longitude, latitude] required")
        longitude, latitude = coordinates
        for coordinate, lower, upper in ((longitude, 139.4, 140.1), (latitude, 35.4, 35.9)):
            if (isinstance(coordinate, bool) or not isinstance(coordinate, (int, float))
                    or not math.isfinite(coordinate) or not lower <= coordinate <= upper):
                raise ValueError(f"{path}.coordinates: Tokyo coordinates required")

    seen_dates = set()
    seen_events = set()
    for day_index, day in enumerate(days):
        day_path = f"days[{day_index}]"
        _shape(day, {"date", "events", "legs"}, set(), day_path)
        day_date = day["date"]
        _date(day_date, f"{day_path}.date")
        if day_date in seen_dates:
            raise ValueError(f"{day_path}.date: duplicate date {day_date}")
        seen_dates.add(day_date)

        events = day["events"]
        if not isinstance(events, list) or len(events) < 2:
            raise ValueError(f"{day_path}.events: at least two events required")
        previous_time = None
        for event_index, event in enumerate(events):
            event_path = f"{day_path}.events[{event_index}]"
            _shape(event, {"id", "time", "placeId"}, {"transactionId"}, event_path)
            _string(event["id"], f"{event_path}.id")
            if event["id"] in seen_events:
                raise ValueError(f"{event_path}.id: duplicate id {event['id']}")
            seen_events.add(event["id"])
            _time(event["time"], f"{event_path}.time")
            if previous_time is not None and event["time"] <= previous_time:
                raise ValueError(f"{event_path}.time: events must be chronological")
            previous_time = event["time"]
            _string(event["placeId"], f"{event_path}.placeId")
            if event["placeId"] not in places:
                raise ValueError(f"{event_path}.placeId: unknown place")
            if "transactionId" in event:
                _string(event["transactionId"], f"{event_path}.transactionId")

        legs = day["legs"]
        if not isinstance(legs, list) or len(legs) != len(events) - 1:
            raise ValueError(f"{day_path}.legs: one leg per adjacent event pair required")
        for leg_index, leg in enumerate(legs):
            leg_path = f"{day_path}.legs[{leg_index}]"
            _shape(leg, {"fromEventId", "toEventId"},
                   {"modeHint", "transportTransactionId", "viaPlaceIds"}, leg_path)
            if leg["fromEventId"] != events[leg_index]["id"]:
                raise ValueError(f"{leg_path}.fromEventId: wrong event")
            if leg["toEventId"] != events[leg_index + 1]["id"]:
                raise ValueError(f"{leg_path}.toEventId: wrong event")
            if "modeHint" in leg and leg["modeHint"] not in ("walk", "train", "bus"):
                raise ValueError(f"{leg_path}.modeHint: unsupported mode")
            if "transportTransactionId" in leg:
                _string(leg["transportTransactionId"], f"{leg_path}.transportTransactionId")
            if leg.get("modeHint") in ("train", "bus") and "transportTransactionId" not in leg:
                raise ValueError(f"{leg_path}.transportTransactionId: required for transit")
            if "viaPlaceIds" in leg:
                via_places = leg["viaPlaceIds"]
                if not isinstance(via_places, list):
                    raise ValueError(f"{leg_path}.viaPlaceIds: array required")
                for via_place_id in via_places:
                    _string(via_place_id, f"{leg_path}.viaPlaceIds")
                    if via_place_id not in places:
                        raise ValueError(f"{leg_path}.viaPlaceIds: unknown place {via_place_id}")

    return value
