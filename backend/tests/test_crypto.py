import pytest

from app.config import get_settings
from app.services import crypto


@pytest.fixture(autouse=True)
def _secret(monkeypatch):
    monkeypatch.setenv("NERVETRACK_SECRET_KEY", "test-secret")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_encrypt_decrypt_round_trip():
    token = crypto.encrypt("sk-abc123")
    assert token != "sk-abc123"
    assert crypto.decrypt(token) == "sk-abc123"


def test_missing_secret_raises(monkeypatch):
    monkeypatch.setenv("NERVETRACK_SECRET_KEY", "")
    get_settings.cache_clear()
    with pytest.raises(RuntimeError, match="NERVETRACK_SECRET_KEY"):
        crypto.encrypt("x")
