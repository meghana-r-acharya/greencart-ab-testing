DROP TABLE IF EXISTS sessions;
CREATE TABLE sessions (
    session_id    INTEGER PRIMARY KEY,
    variant       TEXT    NOT NULL CHECK (variant IN ('control', 'treatment')),
    device        TEXT    NOT NULL,
    city          TEXT    NOT NULL,
    session_date  TEXT    NOT NULL,
    converted     INTEGER NOT NULL CHECK (converted IN (0, 1)),
    order_value   REAL    NOT NULL DEFAULT 0,
    furthest_step INTEGER NOT NULL CHECK (furthest_step BETWEEN 1 AND 4)
);
CREATE INDEX idx_sessions_variant ON sessions (variant);
