-- Timestamped note log + checkbox completion times.
-- Timestamps are naive UTC ISO-8601 text, matching the rest of the schema.

CREATE TABLE notes (
    id UUID PRIMARY KEY DEFAULT (lower(hex(randomblob(4))||'-'||hex(randomblob(2))||'-'||hex(randomblob(2))||'-'||hex(randomblob(2))||'-'||hex(randomblob(6)))),
    daily_entry_id UUID NOT NULL REFERENCES daily_entries (id),
    occurred_at TIMESTAMP NOT NULL,
    body TEXT NOT NULL,
    source TEXT,
    created_at TIMESTAMP DEFAULT (strftime('%Y-%m-%dT%H:%M:%f','now')),
    updated_at TIMESTAMP DEFAULT (strftime('%Y-%m-%dT%H:%M:%f','now'))
);

ALTER TABLE daily_entries ADD COLUMN strengthening_done_at TIMESTAMP;
ALTER TABLE daily_entries ADD COLUMN stretches_morning_at TIMESTAMP;
ALTER TABLE daily_entries ADD COLUMN stretches_night_at TIMESTAMP;
ALTER TABLE daily_entries ADD COLUMN iced_at TIMESTAMP;

INSERT INTO notes (daily_entry_id, occurred_at, body, source)
SELECT id, updated_at, notes, NULL
FROM daily_entries
WHERE notes IS NOT NULL AND trim(notes) <> '';

ALTER TABLE daily_entries DROP COLUMN notes;
