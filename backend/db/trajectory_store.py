"""Persist and read the trajectory timeline in SQLite."""

import sqlite3
import json


def detach_trajectory_references(connection: sqlite3.Connection, ids: set[str]) -> int:
    """Detach deleted purchases and fares in the caller's transaction."""
    affected = 0
    for transaction_id in ids:
        affected += connection.execute(
            "UPDATE trajectory_events SET transaction_id = NULL WHERE transaction_id = ?",
            (transaction_id,),
        ).rowcount
        affected += connection.execute(
            "UPDATE trajectory_legs SET transport_transaction_id = NULL, mode_hint = NULL, mode_evidence = 'inferred', mode_evidence_note = '交通費の取引が削除されたため推定' "
            "WHERE transport_transaction_id = ?", (transaction_id,),
        ).rowcount
    if affected:
        connection.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('trajectory_modified', '1')")
    return affected


def replace_trajectory(connection: sqlite3.Connection, timeline: dict) -> None:
    """Replace trajectory rows with a validated timeline in the caller's transaction."""
    for table in (
        "trajectory_leg_via_places", "trajectory_legs", "trajectory_events",
        "trajectory_days", "trajectory_places",
    ):
        connection.execute(f"DELETE FROM {table}")

    connection.executemany("""
        INSERT INTO trajectory_places (id, name, address, longitude, latitude, source_url, place_evidence, attribution, sources_json, geocoding_json, coordinate_evidence_json, provider, provider_place_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        (place_id, place["name"], place["address"], place.get("coordinates", [None,None])[0],
         place.get("coordinates", [None,None])[1], place["sourceUrl"], place.get("placeEvidence", "legacy"), place.get("attribution"), json.dumps(place.get("sources", []), ensure_ascii=False), json.dumps(place["geocoding"], ensure_ascii=False) if "geocoding" in place else None, json.dumps(place["coordinateEvidence"], ensure_ascii=False) if "coordinateEvidence" in place else None, place.get('provider'), place.get('providerPlaceId'))
        for place_id, place in timeline["places"].items()
    ))

    for day in timeline["days"]:
        day_date = day["date"]
        connection.execute("INSERT INTO trajectory_days (date) VALUES (?)", (day_date,))
        connection.executemany("""
            INSERT INTO trajectory_events (id, day_date, position, time, place_id, transaction_id, time_evidence, time_evidence_note)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            (event["id"], day_date, position, event["time"], event["placeId"],
             event.get("transactionId"), event.get("timeEvidence", "legacy"), event.get("timeEvidenceNote"))
            for position, event in enumerate(day["events"])
        ))
        event_positions = {event["id"]: position for position, event in enumerate(day["events"])}
        for leg in day["legs"]:
            position = event_positions[leg["fromEventId"]]
            connection.execute("""
                INSERT INTO trajectory_legs
                    (day_date, position, from_event_id, to_event_id, mode_hint,
                     transport_transaction_id, has_via_places, mode_evidence, mode_evidence_note)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                day_date, position, leg["fromEventId"], leg["toEventId"],
                leg.get("modeHint"), leg.get("transportTransactionId"),
                int("viaPlaceIds" in leg), leg.get("modeEvidence", "legacy"), leg.get("modeEvidenceNote"),
            ))
            connection.executemany("""
                INSERT INTO trajectory_leg_via_places
                    (day_date, leg_position, via_position, place_id)
                VALUES (?, ?, ?, ?)
            """, (
                (day_date, position, via_position, place_id)
                for via_position, place_id in enumerate(leg.get("viaPlaceIds", []))
            ))


def read_trajectory_day(connection: sqlite3.Connection, date: str) -> dict | None:
    """Rebuild the existing date-scoped API payload from SQLite rows."""
    day = connection.execute("SELECT date FROM trajectory_days WHERE date = ?", (date,)).fetchone()
    if day is None:
        return None

    events = []
    place_ids = set()
    for row in connection.execute("""
        SELECT id, time, place_id, transaction_id, time_evidence, time_evidence_note
        FROM trajectory_events WHERE day_date = ? ORDER BY position
    """, (date,)):
        event = {"id": row["id"], "time": row["time"], "placeId": row["place_id"], "timeEvidence": row["time_evidence"], "timeEvidenceNote": row["time_evidence_note"]}
        if row["transaction_id"] is not None:
            event["transactionId"] = row["transaction_id"]
        events.append(event)
        place_ids.add(row["place_id"])

    legs = []
    for row in connection.execute("""
        SELECT position, from_event_id, to_event_id, mode_hint,
               transport_transaction_id, has_via_places, mode_evidence, mode_evidence_note
        FROM trajectory_legs WHERE day_date = ? ORDER BY position
    """, (date,)):
        leg = {"fromEventId": row["from_event_id"], "toEventId": row["to_event_id"], "modeEvidence": row["mode_evidence"], "modeEvidenceNote": row["mode_evidence_note"]}
        if row["mode_hint"] is not None:
            leg["modeHint"] = row["mode_hint"]
        if row["transport_transaction_id"] is not None:
            leg["transportTransactionId"] = row["transport_transaction_id"]
        if row["has_via_places"]:
            via = [item["place_id"] for item in connection.execute("""
                SELECT place_id FROM trajectory_leg_via_places
                WHERE day_date = ? AND leg_position = ? ORDER BY via_position
            """, (date, row["position"]))]
            leg["viaPlaceIds"] = via
            place_ids.update(via)
        legs.append(leg)

    placeholders = ",".join("?" for _ in place_ids)
    places = {}
    if place_ids:
        for row in connection.execute(f"""
            SELECT *
            FROM trajectory_places WHERE id IN ({placeholders}) ORDER BY rowid
        """, tuple(place_ids)):
            places[row["id"]] = _place_record(row)
    return {"places": places, "days": [{"date": date, "events": events, "legs": legs}]}


def read_trajectory_timeline(connection: sqlite3.Connection) -> dict:
    """Read every saved place and day, including places not yet used by a day."""
    places = {}
    for row in connection.execute("""
        SELECT *
        FROM trajectory_places ORDER BY rowid
    """):
        places[row["id"]] = _place_record(row)
    days = [
        read_trajectory_day(connection, row["date"])["days"][0]
        for row in connection.execute("SELECT date FROM trajectory_days ORDER BY date")
    ]
    return {"places": places, "days": days}


def _place_record(row):
    value={'name':row['name'],'address':row['address'],'sourceUrl':row['source_url'],'placeEvidence':row['place_evidence']}
    if row['provider']=='google':
        return {**value,'provider':'google','providerPlaceId':row['provider_place_id']}
    return {**value,'coordinates':[row['longitude'],row['latitude']],'attribution':row['attribution'],
        **({'sources':json.loads(row['sources_json'])} if json.loads(row['sources_json']) else {}),
        **({'geocoding':json.loads(row['geocoding_json'])} if row['geocoding_json'] else {}),
        **({'coordinateEvidence':json.loads(row['coordinate_evidence_json'])} if row['coordinate_evidence_json'] else {})}
