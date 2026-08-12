"""Per-user LLM provider settings: CRUD + config resolution.

The API key is stored Fernet-encrypted and only ever decrypted here at call
time. ``get_settings_out`` returns a client-safe view (boolean, never the key).
"""

from __future__ import annotations

from uuid import UUID

from app.db import Database
from app.models.ai import LlmSettingsIn, LlmSettingsOut, ResolvedLlmConfig
from app.services import crypto, url_guard


class LlmBaseUrlBlocked(Exception):
    """A stored base_url no longer passes the SSRF guard.

    Distinct from the ValueError save_settings raises on invalid input: this
    fires at request time (resolve_config_async) for a base_url that was
    valid when saved but is no longer permitted — auth_mode changed, the
    allowlist changed, or DNS now resolves it somewhere private.
    """


def _row(db: Database, user_id: UUID) -> dict | None:
    return db.query_one("SELECT * FROM llm_settings WHERE user_id = ?", [user_id])


def get_settings_out(db: Database, user_id: UUID) -> LlmSettingsOut:
    row = _row(db, user_id)
    if row is None:
        return LlmSettingsOut()
    return LlmSettingsOut(
        provider=row["provider"],
        model=row["model"],
        base_url=row["base_url"],
        api_key_set=bool(row["api_key_enc"]),
        configured=bool(row["model"]),
    )


def save_settings(db: Database, user_id: UUID, data: LlmSettingsIn) -> LlmSettingsOut:
    existing = _row(db, user_id)
    # api_key: None = keep existing; "" = clear; other = (re)encrypt.
    if data.api_key is None:
        api_key_enc = existing["api_key_enc"] if existing else None
    elif data.api_key == "":
        api_key_enc = None
    else:
        api_key_enc = crypto.encrypt(data.api_key)

    base_url = data.base_url or None
    if base_url is not None:
        url_guard.validate_llm_base_url(base_url)  # raises ValueError -> 400
    with db.cursor():
        db.execute(
            """
            INSERT INTO llm_settings (user_id, provider, model, api_key_enc, base_url, updated_at)
            VALUES (?, ?, ?, ?, ?, strftime('%Y-%m-%dT%H:%M:%f','now'))
            ON CONFLICT (user_id) DO UPDATE SET
                provider = excluded.provider,
                model = excluded.model,
                api_key_enc = excluded.api_key_enc,
                base_url = excluded.base_url,
                updated_at = excluded.updated_at
            """,
            [user_id, data.provider, data.model, api_key_enc, base_url],
        )
    return get_settings_out(db, user_id)


def resolve_config(db: Database, user_id: UUID) -> ResolvedLlmConfig | None:
    row = _row(db, user_id)
    if row is None or not row["model"]:
        return None
    api_key = crypto.decrypt(row["api_key_enc"]) if row["api_key_enc"] else None
    return ResolvedLlmConfig(model=row["model"], api_key=api_key, base_url=row["base_url"])


async def resolve_config_async(db: Database, user_id: UUID) -> ResolvedLlmConfig | None:
    """Like resolve_config, but re-runs the SSRF guard on the stored base_url.

    Call this (not resolve_config) from async endpoints that are about to
    make an outbound LLM call. It closes the save-then-DNS-rebind window and
    catches any base_url stored before this guard existed. Uses the
    non-blocking resolver, so it is safe on the event loop. Raises
    LlmBaseUrlBlocked — not ValueError — so routers can tell "no longer
    allowed" apart from "invalid input" and respond accordingly.
    """
    config = resolve_config(db, user_id)
    if config is not None and config.base_url:
        try:
            await url_guard.validate_llm_base_url_async(config.base_url)
        except ValueError as exc:
            raise LlmBaseUrlBlocked(str(exc)) from exc
    return config
