import json

import pytest

from app.config import get_settings
from app.services import llm


@pytest.fixture(autouse=True)
def _secret(monkeypatch):
    monkeypatch.setenv("NERVETRACK_SECRET_KEY", "test-secret")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_settings_round_trip_hides_key(auth_client):
    r = auth_client.put("/api/v1/ai/settings", json={
        "provider": "anthropic", "model": "anthropic/claude-sonnet-5", "api_key": "sk-secret",
    })
    assert r.status_code == 200
    body = r.json()
    assert body["configured"] is True and body["api_key_set"] is True
    assert "sk-secret" not in json.dumps(body)
    assert auth_client.get("/api/v1/ai/settings").json()["model"] == "anthropic/claude-sonnet-5"


def test_chat_requires_config(auth_client):
    conv = auth_client.post("/api/v1/ai/conversations").json()
    r = auth_client.post(f"/api/v1/ai/conversations/{conv['id']}/messages",
                         json={"content": "hi"})
    assert r.status_code == 409
    assert r.json()["detail"] == "llm_not_configured"


def test_save_settings_rejects_private_base_url(auth_client):
    # auth_client runs in password (multi-user) mode.
    r = auth_client.put("/api/v1/ai/settings", json={
        "provider": "ollama", "model": "ollama/llama3.1", "base_url": "http://10.0.0.1:11434",
    })
    assert r.status_code == 400


def test_chat_blocked_when_stored_base_url_no_longer_allowed(auth_client, db, user_id):
    # Simulate a base_url stored before this guard existed (or one that
    # became disallowed since, e.g. an auth_mode change) by writing it
    # directly rather than through save_settings.
    db.execute(
        """
        INSERT INTO llm_settings (user_id, provider, model, base_url, updated_at)
        VALUES (?, 'ollama', 'ollama/llama3.1', 'http://127.0.0.1:11434',
                strftime('%Y-%m-%dT%H:%M:%f','now'))
        """,
        [user_id],
    )
    conv = auth_client.post("/api/v1/ai/conversations").json()
    r = auth_client.post(f"/api/v1/ai/conversations/{conv['id']}/messages",
                         json={"content": "hi"})
    assert r.status_code == 403


def test_chat_streams_and_persists(auth_client, monkeypatch, db, user_id):
    auth_client.put("/api/v1/ai/settings", json={
        "provider": "anthropic", "model": "anthropic/claude-sonnet-5", "api_key": "k",
    })
    from app.models.pain_instances import PainInstanceCreate
    from app.services import pain_instances as pi
    pi.create_instance(db, user_id, PainInstanceCreate(name="Left sciatic"))

    captured = {}

    async def fake_stream(config, history, run_tool, max_iters=8, extra_context=""):
        captured["extra_context"] = extra_context
        yield {"type": "token", "text": "Hi "}
        yield {"type": "token", "text": "there"}
        yield {"type": "final", "content": "Hi there"}

    monkeypatch.setattr(llm, "stream_chat", fake_stream)

    conv = auth_client.post("/api/v1/ai/conversations").json()
    with auth_client.stream("POST", f"/api/v1/ai/conversations/{conv['id']}/messages",
                            json={"content": "hello"}) as r:
        assert r.status_code == 200
        text = "".join(r.iter_text())
    assert "Hi there" in text
    assert "Left sciatic" in captured["extra_context"]

    detail = auth_client.get(f"/api/v1/ai/conversations/{conv['id']}").json()
    roles = [(m["role"], m["content"]) for m in detail["messages"]]
    assert ("user", "hello") in roles
    assert ("assistant", "Hi there") in roles


def test_weekly_draft(auth_client, monkeypatch, db, user_id):
    from datetime import date
    db.execute("INSERT INTO daily_entries (user_id, entry_date, status) VALUES (?, ?, 'G')",
               [user_id, date(2026, 6, 22)])
    auth_client.put("/api/v1/ai/settings", json={
        "provider": "anthropic", "model": "m", "api_key": "k"})

    async def fake_draft(config, bundle, extra_context=""):
        from app.models.ai import WeeklyDraftResponse
        return WeeklyDraftResponse(key_observations="obs", next_steps="plan")

    monkeypatch.setattr(llm, "draft_weekly", fake_draft)
    r = auth_client.post("/api/v1/ai/weekly-draft/2026-06-22")
    assert r.status_code == 200
    assert r.json() == {"key_observations": "obs", "next_steps": "plan"}
