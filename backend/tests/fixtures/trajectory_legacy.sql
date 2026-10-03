BEGIN TRANSACTION;
CREATE TABLE trajectory_days (
            date TEXT PRIMARY KEY
        );
CREATE TABLE trajectory_events (
            id TEXT PRIMARY KEY,
            day_date TEXT NOT NULL REFERENCES trajectory_days(date) ON DELETE CASCADE,
            position INTEGER NOT NULL CHECK (position >= 0),
            time TEXT NOT NULL,
            place_id TEXT NOT NULL REFERENCES trajectory_places(id),
            transaction_id TEXT,
            UNIQUE (day_date, position)
        );
CREATE TABLE trajectory_leg_via_places (
            day_date TEXT NOT NULL,
            leg_position INTEGER NOT NULL,
            via_position INTEGER NOT NULL CHECK (via_position >= 0),
            place_id TEXT NOT NULL REFERENCES trajectory_places(id),
            PRIMARY KEY (day_date, leg_position, via_position),
            FOREIGN KEY (day_date, leg_position)
                REFERENCES trajectory_legs(day_date, position) ON DELETE CASCADE
        );
CREATE TABLE trajectory_legs (
            day_date TEXT NOT NULL REFERENCES trajectory_days(date) ON DELETE CASCADE,
            position INTEGER NOT NULL CHECK (position >= 0),
            from_event_id TEXT NOT NULL REFERENCES trajectory_events(id),
            to_event_id TEXT NOT NULL REFERENCES trajectory_events(id),
            mode_hint TEXT,
            transport_transaction_id TEXT,
            has_via_places INTEGER NOT NULL CHECK (has_via_places IN (0, 1)),
            PRIMARY KEY (day_date, position)
        );
CREATE TABLE trajectory_places (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            address TEXT NOT NULL,
            longitude REAL NOT NULL CHECK (longitude BETWEEN 139.4 AND 140.1),
            latitude REAL NOT NULL CHECK (latitude BETWEEN 35.4 AND 35.9),
            source_url TEXT NOT NULL
        );
COMMIT;