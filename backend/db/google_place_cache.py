"""Temporary Google coordinates, separated from durable trajectory records."""
import math
from agent.google_places import valid_place_id

TTL_SECONDS=30*86400

def write_cached_coordinates(connection, place_id, coordinates, obtained_at):
    if not valid_place_id(place_id) or len(coordinates)!=2 or any(isinstance(n,bool) or not isinstance(n,(float,int)) or not math.isfinite(n) for n in (*coordinates,obtained_at)) or not (-180<=coordinates[0]<=180 and -90<=coordinates[1]<=90):
        raise ValueError('Invalid Google coordinate cache entry')
    connection.execute('INSERT OR REPLACE INTO google_place_coordinates VALUES (?,?,?,?,?)',
        (place_id,*coordinates,obtained_at,obtained_at+TTL_SECONDS))

def purge_expired_coordinates(connection, now):
    return connection.execute('DELETE FROM google_place_coordinates WHERE expires_at<=?',(now,)).rowcount

def read_cached_coordinates(connection, place_id, now):
    purge_expired_coordinates(connection,now)
    row=connection.execute('SELECT longitude,latitude FROM google_place_coordinates WHERE place_id=? AND expires_at>?',(place_id,now)).fetchone()
    return (row[0],row[1]) if row else None
