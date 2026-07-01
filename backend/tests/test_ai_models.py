from app.models.ai import LlmSettingsIn, LlmSettingsOut, WeeklyDraftResponse


def test_settings_in_defaults():
    s = LlmSettingsIn(provider="anthropic", model="anthropic/claude-sonnet-5")
    assert s.api_key is None and s.base_url is None


def test_settings_out_shape():
    out = LlmSettingsOut(provider="ollama", model="ollama/llama3.1", configured=True)
    assert out.api_key_set is False
    assert "api_key" not in out.model_dump()


def test_weekly_draft_fields():
    d = WeeklyDraftResponse(key_observations="a", next_steps="b")
    assert d.key_observations == "a" and d.next_steps == "b"
