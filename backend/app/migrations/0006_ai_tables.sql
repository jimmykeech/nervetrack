-- Per-user LLM provider configuration. api_key_enc is Fernet-encrypted text;
-- NULL means no key (e.g. local Ollama). One row per user.
CREATE TABLE llm_settings (
    user_id UUID PRIMARY KEY REFERENCES users (id),
    provider TEXT,
    model TEXT,
    api_key_enc TEXT,
    base_url TEXT,
    updated_at TIMESTAMP DEFAULT (strftime('%Y-%m-%dT%H:%M:%f','now'))
);

-- Persisted chat threads.
CREATE TABLE conversations (
    id UUID PRIMARY KEY DEFAULT (lower(hex(randomblob(4))||'-'||hex(randomblob(2))||'-'||hex(randomblob(2))||'-'||hex(randomblob(2))||'-'||hex(randomblob(6)))),
    user_id UUID NOT NULL REFERENCES users (id),
    title TEXT,
    created_at TIMESTAMP DEFAULT (strftime('%Y-%m-%dT%H:%M:%f','now')),
    updated_at TIMESTAMP DEFAULT (strftime('%Y-%m-%dT%H:%M:%f','now'))
);

CREATE INDEX idx_conversations_user ON conversations (user_id, updated_at);

-- Individual turns. role in ('user','assistant','tool'); tool_calls_json holds
-- the serialized tool calls/results for exact thread replay.
CREATE TABLE messages (
    id UUID PRIMARY KEY DEFAULT (lower(hex(randomblob(4))||'-'||hex(randomblob(2))||'-'||hex(randomblob(2))||'-'||hex(randomblob(2))||'-'||hex(randomblob(6)))),
    conversation_id UUID NOT NULL REFERENCES conversations (id) ON DELETE CASCADE,
    role TEXT NOT NULL,
    content TEXT,
    tool_calls_json TEXT,
    created_at TIMESTAMP DEFAULT (strftime('%Y-%m-%dT%H:%M:%f','now'))
);

CREATE INDEX idx_messages_conversation ON messages (conversation_id, created_at);
