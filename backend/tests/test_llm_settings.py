import pytest

from app.config import get_settings
from app.models.ai import LlmSettingsIn
from app.services import llm_settings


@pytest.fixture(autouse=True)
def _secret(monkeypatch):
    monkeypatch.setenv("NERVETRACK_SECRET_KEY", "test-secret")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture()
def none_mode(monkeypatch):
    # conftest's autouse _cookie_auth_mode fixture defaults every test to
    # "password"; override back to "none" for the tests that need it.
    monkeypatch.setenv("NERVETRACK_AUTH_MODE", "none")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_unset_is_not_configured(db, user_id):
    out = llm_settings.get_settings_out(db, user_id)
    assert out.configured is False and out.api_key_set is False
    assert llm_settings.resolve_config(db, user_id) is None


def test_save_then_resolve_decrypts(db, user_id):
    llm_settings.save_settings(
        db, user_id,
        LlmSettingsIn(provider="anthropic", model="anthropic/claude-sonnet-5", api_key="sk-xyz"),
    )
    out = llm_settings.get_settings_out(db, user_id)
    assert out.configured is True and out.api_key_set is True
    assert "sk-xyz" not in out.model_dump_json()  # key never surfaced

    cfg = llm_settings.resolve_config(db, user_id)
    assert cfg is not None
    assert cfg.model == "anthropic/claude-sonnet-5"
    assert cfg.api_key == "sk-xyz"


def test_api_key_none_preserves_existing(db, user_id):
    llm_settings.save_settings(
        db, user_id,
        LlmSettingsIn(provider="anthropic", model="m1", api_key="sk-1"),
    )
    llm_settings.save_settings(
        db, user_id,
        LlmSettingsIn(provider="anthropic", model="m2", api_key=None),  # model change only
    )
    cfg = llm_settings.resolve_config(db, user_id)
    assert cfg.model == "m2" and cfg.api_key == "sk-1"


def test_empty_api_key_clears(db, user_id):
    llm_settings.save_settings(
        db, user_id, LlmSettingsIn(provider="ollama", model="ollama/llama3.1", api_key="sk-1"),
    )
    llm_settings.save_settings(
        db, user_id, LlmSettingsIn(provider="ollama", model="ollama/llama3.1", api_key=""),
    )
    out = llm_settings.get_settings_out(db, user_id)
    assert out.api_key_set is False
    assert llm_settings.resolve_config(db, user_id).api_key is None


def test_save_private_base_url_rejected_multi_user(db, user_id):
    # conftest defaults auth_mode to "password" (multi-user).
    with pytest.raises(ValueError):
        llm_settings.save_settings(
            db, user_id,
            LlmSettingsIn(provider="ollama", model="ollama/llama3.1", base_url="http://10.0.0.1:11434"),
        )
    # Rejected save must not persist.
    assert llm_settings.resolve_config(db, user_id) is None


def test_save_custom_base_url_rejects_provider_without_guarded_transport(db, user_id):
    with pytest.raises(ValueError, match="custom base_url requires"):
        llm_settings.save_settings(
            db,
            user_id,
            LlmSettingsIn(
                provider="cohere",
                model="cohere/command-r",
                base_url="https://llm.example",
            ),
        )


def test_save_localhost_base_url_allowed_in_none_mode(db, user_id, none_mode):
    out = llm_settings.save_settings(
        db, user_id,
        LlmSettingsIn(provider="ollama", model="ollama/llama3.1", base_url="http://127.0.0.1:11434"),
    )
    assert out.base_url == "http://127.0.0.1:11434"
    cfg = llm_settings.resolve_config(db, user_id)
    assert cfg.base_url == "http://127.0.0.1:11434"
