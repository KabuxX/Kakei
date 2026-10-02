"""Persist and read the trajectory timeline in SQLite."""

import sqlite3


def replace_trajectory(connection: sqlite3.Connection, timeline: dict) -> None:
    """Replace trajectory rows with a validated timeline in the caller's transaction."""
    for table in (
        "trajectory_leg_via_places", "trajectory_legs", "trajectory_events",
        "trajectory_days", "trajectory_places",
    ):
        connection.execute(f"DELETE FROM {table}")

    connection.executemany("""
        INSERT INTO trajectory_places (id, name, address, longitude, latitude, source_url)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        (place_id, place["name"], place["address"], place["coordinates"][0],
         place["coordinates"][1], place["sourceUrl"])
        for place_id, place in timeline["places"].items()
    ))

    for day in timeline["days"]:
        day_date = day["date"]
        connection.execute("INSERT INTO trajectory_days (date) VALUES (?)", (day_date,))
        connection.executemany("""
            INSERT INTO trajectory_events (id, day_date, position, time, place_id, transaction_id)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            (event["id"], day_date, position, event["time"], event["placeId"],
             event.get("transactionId"))
            for position, event in enumerate(day["events"])
        ))
        for position, leg in enumerate(day["legs"]):
            connection.execute("""
                INSERT INTO trajectory_legs
                    (day_date, position, from_event_id, to_event_id, mode_hint,
                     transport_transaction_id, has_via_places)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                day_date, position, leg["fromEventId"], leg["toEventId"],
                leg.get("modeHint"), leg.get("transportTransactionId"),
                int("viaPlaceIds" in leg),
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
        SELECT id, time, place_id, transaction_id
        FROM trajectory_events WHERE day_date = ? ORDER BY position
    """, (date,)):
        event = {"id": row["id"], "time": row["time"], "placeId": row["place_id"]}
        if row["transaction_id"] is not None:
            event["transactionId"] = row["transaction_id"]
        events.append(event)
        place_ids.add(row["place_id"])

    legs = []
    for row in connection.execute("""
        SELECT position, from_event_id, to_event_id, mode_hint,
               transport_transaction_id, has_via_places
        FROM trajectory_legs WHERE day_date = ? ORDER BY position
    """, (date,)):
        leg = {"fromEventId": row["from_event_id"], "toEventId": row["to_event_id"]}
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
            SELECT id, name, address, longitude, latitude, source_url
            FROM trajectory_places WHERE id IN ({placeholders}) ORDER BY rowid
        """, tuple(place_ids)):
            places[row["id"]] = {
                "name": row["name"], "address": row["address"],
                "coordinates": [row["longitude"], row["latitude"]],
                "sourceUrl": row["source_url"],
            }
    return {"places": places, "days": [{"date": date, "events": events, "legs": legs}]}
