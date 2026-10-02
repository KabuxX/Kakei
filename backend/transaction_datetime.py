"""Validation and deterministic completion for transaction datetimes."""

import re
from datetime import datetime


_DATE_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}\Z")
_DATETIME_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}\Z")


def parse_transaction_datetime(
    value: object, *, allow_date_only: bool = False
) -> tuple[str, bool]:
    """Validate a local transaction date and return it with its estimated flag."""
    if not isinstance(value, str):
        raise ValueError("Transaction date must be a string")

    if _DATE_PATTERN.fullmatch(value):
        try:
            datetime.strptime(value, "%Y-%m-%d")
        except ValueError as error:
            raise ValueError("Transaction date is not a real calendar date") from error
        if allow_date_only:
            return value, True
        raise ValueError("Transaction date must include hours and minutes")

    if _DATETIME_PATTERN.fullmatch(value):
        try:
            datetime.strptime(value, "%Y-%m-%dT%H:%M")
        except ValueError as error:
            raise ValueError("Transaction datetime is not valid") from error
        return value, False

    raise ValueError("Transaction datetime must use YYYY-MM-DDTHH:mm")


def assign_estimated_datetimes(records: list[dict]) -> list[dict]:
    """Copy records and assign stable, distinct minutes to date-only rows."""
    result = [dict(record) for record in records]
    groups: dict[str, list[tuple[str, int]]] = {}

    for index, record in enumerate(records):
        date_value, is_estimated = parse_transaction_datetime(
            record.get("date"), allow_date_only=True
        )
        if is_estimated:
            if not isinstance(record.get("id"), str):
                raise ValueError("Date-only transaction records need a string id")
            groups.setdefault(date_value, []).append((record["id"], index))

    for date_value, rows in groups.items():
        count = len(rows)
        if count > 1440:
            raise ValueError(f"More than 1440 date-only transactions on {date_value}")

        for position, (_, record_index) in enumerate(sorted(rows, key=lambda row: row[0])):
            if count == 1:
                minute_of_day = 12 * 60
            elif count <= 840:
                minute_of_day = 8 * 60 + ((position + 1) * 840 // (count + 1))
            else:
                minute_of_day = (position + 1) * 1440 // (count + 1)
            hour, minute = divmod(minute_of_day, 60)
            result[record_index]["date"] = f"{date_value}T{hour:02d}:{minute:02d}"
            result[record_index]["timeEstimated"] = True

    return result
