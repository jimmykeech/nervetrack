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


def test_chat_streams_and_persists(auth_client, monkeypatch):
    auth_client.put("/api/v1/ai/settings", json={
        "provider": "anthropic", "model": "anthropic/claude-sonnet-5", "api_key": "k",
    })

    async def fake_stream(config, history, run_tool, max_iters=8):
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

    async def fake_draft(config, bundle):
        from app.models.ai import WeeklyDraftResponse
        return WeeklyDraftResponse(key_observations="obs", next_steps="plan")

    monkeypatch.setattr(llm, "draft_weekly", fake_draft)
    r = auth_client.post("/api/v1/ai/weekly-draft/2026-06-22")
    assert r.status_code == 200
    assert r.json() == {"key_observations": "obs", "next_steps": "plan"}
