"""Validate sample fixtures and coordinate guarded replacement."""

import json
from pathlib import Path

from db.sample_replacement import replace_sample_rows
from services.trajectory_validation import load_timeline
from services.validation import normalize_transaction
from transaction_datetime import assign_estimated_datetimes


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_constant(value):
    raise ValueError(f"Invalid JSON number: {value}")


def _load_records(path: Path, *, unique_content: bool) -> list[dict]:
    with Path(path).open(encoding="utf-8") as source:
        records = json.load(source, object_pairs_hook=_unique_object, parse_constant=_reject_constant)
    if not isinstance(records, list) or not records:
        raise ValueError(f"{path}: nonempty transaction array required")
    seen_ids = set()
    seen_content = set()
    normalized_records = []
    for index, record in enumerate(records):
        label = f"{path}: transaction {index + 1}"
        if not isinstance(record, dict):
            raise ValueError(f"{label}: object required")
        fields = {"id", "title", "date", "type", "category", "amount"}
        if record.get("type") == "expense":
            fields.update({"merchant", "paymentMethod", "items"})
            if not isinstance(record.get("merchant"), str):
                raise ValueError(f"{label}: merchant string required")
            if not isinstance(record.get("paymentMethod"), str):
                raise ValueError(f"{label}: paymentMethod string required")
            items = record.get("items")
            if not isinstance(items, list) or any(
                not isinstance(item, dict) or item.keys() != {"name", "amount"}
                for item in items
            ):
                raise ValueError(f"{label}: complete items required")
        if record.keys() != fields:
            raise ValueError(f"{label}: complete transaction fields required")
        normalized = normalize_transaction(record, import_mode=True)
        # Import normalization is intentionally tolerant elsewhere; this command
        # must reject any input whose fields or items would be changed or dropped.
        if {key: value for key, value in normalized.items() if key != "timeEstimated"} != record:
            raise ValueError(f"{label}: normalization would change transaction data")
        transaction_id = normalized["id"]
        if not transaction_id.startswith("sample-") or transaction_id in seen_ids:
            raise ValueError(f"{label}: unique sample- ID required")
        seen_ids.add(transaction_id)
        content = json.dumps({key: value for key, value in normalized.items()
                              if key not in {"id", "date"}}, sort_keys=True, ensure_ascii=False)
        if unique_content and content in seen_content:
            raise ValueError(f"{label}: duplicate transaction content")
        seen_content.add(content)
        normalized_records.append(normalized)
    return assign_estimated_datetimes(normalized_records)


def _check_transaction_references(timeline: dict, records: list[dict]) -> None:
    dates = {record["id"]: record["date"] for record in records}
    for day in timeline["days"]:
        for entries, field in ((day["events"], "transactionId"),
                               (day["legs"], "transportTransactionId")):
            for entry in entries:
                if field in entry and dates.get(entry[field], "")[:10] != day["date"]:
                    raise ValueError(f"{day['date']}: {field} must reference a same-date transaction")


def replace_samples(db_path: Path, old_path: Path, new_path: Path,
                    timeline_path: Path, backup_path: Path) -> dict[str, int]:
    """Validate every fixture before backing up and replacing saved samples."""
    old_records = _load_records(old_path, unique_content=False)
    new_records = _load_records(new_path, unique_content=True)
    timeline = load_timeline(timeline_path)
    _check_transaction_references(timeline, new_records)
    return replace_sample_rows(db_path, backup_path, old_records, new_records, timeline)
