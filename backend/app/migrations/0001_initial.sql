-- Initial NerveTrack schema (Phase 1), SQLite dialect.
-- Timestamps are stored as naive UTC ISO-8601 text; dates as ISO-8601 text.
-- UUID columns store canonical dashed UUID text.

CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT (lower(hex(randomblob(4))||'-'||hex(randomblob(2))||'-'||hex(randomblob(2))||'-'||hex(randomblob(2))||'-'||hex(randomblob(6)))),
    google_sub TEXT UNIQUE,
    email TEXT UNIQUE NOT NULL,
    name TEXT,
    created_at TIMESTAMP DEFAULT (strftime('%Y-%m-%dT%H:%M:%f','now'))
);

CREATE TABLE auth_sessions (
    token_hash TEXT PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users (id),
    created_at TIMESTAMP DEFAULT (strftime('%Y-%m-%dT%H:%M:%f','now')),
    expires_at TIMESTAMP NOT NULL
);

CREATE TABLE daily_entries (
    id UUID PRIMARY KEY DEFAULT (lower(hex(randomblob(4))||'-'||hex(randomblob(2))||'-'||hex(randomblob(2))||'-'||hex(randomblob(2))||'-'||hex(randomblob(6)))),
    user_id UUID NOT NULL REFERENCES users (id),
    entry_date DATE NOT NULL,
    status TEXT CHECK (status IN ('G', 'A', 'R')),
    strengthening_done BOOLEAN DEFAULT FALSE,
    session_intensity DECIMAL(3, 1),
    sharp_pain_episodes INTEGER DEFAULT 0,
    worst_pain DECIMAL(3, 1),
    tingling_level DECIMAL(3, 1),
    tingling_duration_minutes INTEGER,
    stretches_morning BOOLEAN DEFAULT FALSE,
    stretches_night BOOLEAN DEFAULT FALSE,
    sitting_breaks TEXT,
    sleep_quality DECIMAL(2, 1),
    iced BOOLEAN DEFAULT FALSE,
    notes TEXT,
    created_at TIMESTAMP DEFAULT (strftime('%Y-%m-%dT%H:%M:%f','now')),
    updated_at TIMESTAMP DEFAULT (strftime('%Y-%m-%dT%H:%M:%f','now')),
    UNIQUE (user_id, entry_date)
);

CREATE TABLE pain_events (
    id UUID PRIMARY KEY DEFAULT (lower(hex(randomblob(4))||'-'||hex(randomblob(2))||'-'||hex(randomblob(2))||'-'||hex(randomblob(2))||'-'||hex(randomblob(6)))),
    daily_entry_id UUID NOT NULL REFERENCES daily_entries (id),
    occurred_at TIMESTAMP NOT NULL,
    pain_level DECIMAL(3, 1),
    context TEXT
);

CREATE TABLE exercises (
    id UUID PRIMARY KEY DEFAULT (lower(hex(randomblob(4))||'-'||hex(randomblob(2))||'-'||hex(randomblob(2))||'-'||hex(randomblob(2))||'-'||hex(randomblob(6)))),
    user_id UUID NOT NULL REFERENCES users (id),
    name TEXT NOT NULL,
    active BOOLEAN DEFAULT TRUE,
    sort_order INTEGER DEFAULT 0,
    UNIQUE (user_id, name)
);

CREATE TABLE strength_sessions (
    id UUID PRIMARY KEY DEFAULT (lower(hex(randomblob(4))||'-'||hex(randomblob(2))||'-'||hex(randomblob(2))||'-'||hex(randomblob(2))||'-'||hex(randomblob(6)))),
    daily_entry_id UUID NOT NULL REFERENCES daily_entries (id),
    performed_at TIMESTAMP NOT NULL,
    intensity DECIMAL(3, 1),
    notes TEXT
);

CREATE TABLE exercise_logs (
    id UUID PRIMARY KEY DEFAULT (lower(hex(randomblob(4))||'-'||hex(randomblob(2))||'-'||hex(randomblob(2))||'-'||hex(randomblob(2))||'-'||hex(randomblob(6)))),
    session_id UUID NOT NULL REFERENCES strength_sessions (id),
    exercise_id UUID NOT NULL REFERENCES exercises (id),
    sets INTEGER,
    reps INTEGER,
    hold_seconds INTEGER,
    weight_kg DECIMAL(4, 1),
    difficulty DECIMAL(3, 1),
    nerve_response TEXT,
    modification TEXT
);

CREATE TABLE sit_stand_sessions (
    id UUID PRIMARY KEY DEFAULT (lower(hex(randomblob(4))||'-'||hex(randomblob(2))||'-'||hex(randomblob(2))||'-'||hex(randomblob(2))||'-'||hex(randomblob(6)))),
    user_id UUID NOT NULL REFERENCES users (id),
    entry_date DATE NOT NULL,
    posture TEXT NOT NULL CHECK (posture IN ('sitting', 'standing', 'lying', 'walking')),
    started_at TIMESTAMP NOT NULL,
    ended_at TIMESTAMP,
    duration_seconds INTEGER,
    label TEXT
);

CREATE TABLE weekly_summaries (
    id UUID PRIMARY KEY DEFAULT (lower(hex(randomblob(4))||'-'||hex(randomblob(2))||'-'||hex(randomblob(2))||'-'||hex(randomblob(2))||'-'||hex(randomblob(6)))),
    user_id UUID NOT NULL REFERENCES users (id),
    week_start DATE NOT NULL,
    strengthening_sessions INTEGER,
    avg_pain_episodes_per_day DECIMAL(5, 2),
    avg_tingling_level DECIMAL(5, 2),
    worst_pain DECIMAL(3, 1),
    overall_status TEXT CHECK (overall_status IN ('G', 'A', 'R')),
    key_observations TEXT,
    trend_vs_last_week TEXT,
    UNIQUE (user_id, week_start)
);

CREATE TABLE app_settings (
    user_id UUID NOT NULL REFERENCES users (id),
    key TEXT NOT NULL,
    value TEXT,
    PRIMARY KEY (user_id, key)
);
