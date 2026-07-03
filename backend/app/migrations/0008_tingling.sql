-- Tingling timer sessions.

CREATE TABLE tingling_sessions (
    id UUID PRIMARY KEY DEFAULT (lower(hex(randomblob(4))||'-'||hex(randomblob(2))||'-'||hex(randomblob(2))||'-'||hex(randomblob(2))||'-'||hex(randomblob(6)))),
    user_id UUID NOT NULL REFERENCES users (id),
    entry_date DATE NOT NULL,
    level NUMERIC NOT NULL CHECK (level >= 0 AND level <= 10),
    started_at TIMESTAMP NOT NULL,
    ended_at TIMESTAMP,
    duration_seconds INTEGER
);
