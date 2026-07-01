-- Pain instances: per-user catalogue of tracked nerve-pain issues, with
-- many-to-many tagging onto pain jabs and strengthening sessions.

CREATE TABLE pain_instances (
    id UUID PRIMARY KEY DEFAULT (lower(hex(randomblob(4))||'-'||hex(randomblob(2))||'-'||hex(randomblob(2))||'-'||hex(randomblob(2))||'-'||hex(randomblob(6)))),
    user_id UUID NOT NULL REFERENCES users (id),
    name TEXT NOT NULL,
    body_region TEXT,
    background TEXT,
    active BOOLEAN DEFAULT TRUE,
    sort_order INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT (strftime('%Y-%m-%dT%H:%M:%f','now')),
    UNIQUE (user_id, name)
);

CREATE TABLE pain_event_instances (
    pain_event_id UUID NOT NULL REFERENCES pain_events (id),
    instance_id UUID NOT NULL REFERENCES pain_instances (id),
    PRIMARY KEY (pain_event_id, instance_id)
);

CREATE TABLE session_instances (
    session_id UUID NOT NULL REFERENCES strength_sessions (id),
    instance_id UUID NOT NULL REFERENCES pain_instances (id),
    PRIMARY KEY (session_id, instance_id)
);
