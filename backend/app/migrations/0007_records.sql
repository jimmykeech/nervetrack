-- Patient background that sits outside any single condition. One row per user.
CREATE TABLE patient_profile (
    user_id UUID PRIMARY KEY REFERENCES users (id),
    dob DATE,
    sex TEXT,
    height_cm DECIMAL(5, 1),
    weight_kg DECIMAL(5, 1),
    lifestyle TEXT,
    medical_history TEXT,
    updated_at TIMESTAMP DEFAULT (strftime('%Y-%m-%dT%H:%M:%f','now'))
);

-- Dated notes log per condition (mirrors the daily notes table).
CREATE TABLE condition_notes (
    id UUID PRIMARY KEY DEFAULT (lower(hex(randomblob(4))||'-'||hex(randomblob(2))||'-'||hex(randomblob(2))||'-'||hex(randomblob(2))||'-'||hex(randomblob(6)))),
    instance_id UUID NOT NULL REFERENCES pain_instances (id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users (id),
    occurred_at TIMESTAMP NOT NULL,
    body TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT (strftime('%Y-%m-%dT%H:%M:%f','now'))
);

CREATE INDEX idx_condition_notes_instance ON condition_notes (instance_id, occurred_at);

-- Supporting documents (medical reports/imaging). Bytes live in content;
-- owner_type is 'profile' (general) or 'condition' (instance_id set).
CREATE TABLE documents (
    id UUID PRIMARY KEY DEFAULT (lower(hex(randomblob(4))||'-'||hex(randomblob(2))||'-'||hex(randomblob(2))||'-'||hex(randomblob(2))||'-'||hex(randomblob(6)))),
    user_id UUID NOT NULL REFERENCES users (id),
    owner_type TEXT NOT NULL,
    instance_id UUID REFERENCES pain_instances (id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    notes TEXT,
    filename TEXT,
    mime_type TEXT,
    size_bytes INTEGER,
    content BLOB,
    created_at TIMESTAMP DEFAULT (strftime('%Y-%m-%dT%H:%M:%f','now'))
);

CREATE INDEX idx_documents_user ON documents (user_id, owner_type);
CREATE INDEX idx_documents_instance ON documents (instance_id);
