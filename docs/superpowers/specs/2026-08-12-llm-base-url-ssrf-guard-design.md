# SSRF guard on the per-user LLM base_url (issue #13)

**Issue:** [#13](https://github.com/jimmykeech/nervetrack/issues/13) — Security: SSRF via
user-controlled LLM `base_url` (multi-user deployments).

## Problem

`LlmSettingsIn.base_url` (`backend/app/models/ai.py:16`) is accepted from the client,
stored verbatim (`services/llm_settings.py:43`), and passed straight to LiteLLM as
`api_base` (`services/llm.py:33`). There is no scheme restriction, host allowlist, or
private/link-local filtering, so an authenticated user on a multi-user instance can point
the backend's outbound requests at cloud metadata (`169.254.169.254`) or internal
services and trigger them via chat or a weekly draft.

`auth_mode` defaults to `none` (single local user) but supports `password` and `google`
(`config.py:41`). The vulnerability is specific to the latter two.

## Design

A custom `base_url` is a real feature — self-hosted Ollama / LM Studio on localhost — so
the guard is **auth-mode-aware** rather than a blanket private-range ban.

### New module `backend/app/services/url_guard.py`

One validator, used from two places. Raise `ValueError` with a user-facing message on
rejection; return `None` on success.

```python
def validate_llm_base_url(url: str) -> None:
    """Reject base URLs that would let a user aim the backend at internal hosts."""
```

Rules, in order:

1. Parse with `urllib.parse.urlsplit`. Scheme must be `http` or `https` — reject `file:`,
   `ftp:`, `gopher:`, and anything else. A hostname is required.
2. Read settings via `get_settings()`. If `auth_mode == "none"`, stop here: a single local
   user crosses no trust boundary, and `http://127.0.0.1:11434` must keep working.
3. Multi-user (`auth_mode` in `{"password", "google"}`):
   - If the URL's origin (scheme + host + port) matches an entry in the new
     `NERVETRACK_LLM_ALLOWED_BASE_URLS` setting, allow it and skip the remaining checks.
     This is the operator escape hatch for a deliberately-permitted internal gateway.
   - Otherwise require `https`.
   - If the hostname is a literal IP, check it directly. Otherwise resolve it with
     `socket.getaddrinfo` and check **every** returned A/AAAA address.
   - Reject if any address is loopback, link-local, private, reserved, multicast or
     unspecified. `169.254.169.254` and `fd00:ec2::254` are covered by the link-local and
     private checks respectively — assert this in tests rather than special-casing.
   - A DNS resolution failure is a rejection, not a pass.

Provide an async twin for the request-time path so the event loop is not blocked:

```python
async def validate_llm_base_url_async(url: str) -> None:
```

It must use `asyncio.get_running_loop().getaddrinfo(...)` rather than the blocking
`socket` call. Share the scheme/allowlist/IP-classification logic between the two
entry points; only resolution differs.

### Config (`backend/app/config.py`)

- `llm_allowed_base_urls: str = ""` — comma-separated origins, following the existing
  `allowed_emails` pattern (line 34).
- A `llm_allowed_base_url_set()` helper alongside `allowed_email_set()` (line 51),
  normalising each entry to a lowercase scheme+host+port origin.
- An `is_multi_user()` helper returning `auth_mode in ("password", "google")`.

### Enforcement point 1 — save

`llm_settings.save_settings` validates `base_url` before persisting. The router
(`routers/ai.py:35-39`) catches `ValueError` and raises `HTTPException(400, str(exc))`,
matching the `try/except ValueError` style already used in `routers/sessions.py:28-30`.
The settings page (`frontend/src/routes/settings/+page.svelte:43`) should surface the
message; check how it currently renders API errors and follow that.

### Enforcement point 2 — request

`resolve_config` re-validates before each call. This closes the save-then-DNS-rebind path
and also catches any `base_url` stored before this fix.

`resolve_config` is currently sync and called from async endpoints
(`routers/ai.py:75,114`). Do **not** make it do blocking DNS. Either move the
re-validation into the async callers via `validate_llm_base_url_async`, or make
`resolve_config` async — pick whichever fits the router shape with the least churn, and
keep the two call sites consistent.

On rejection at request time, surface a distinct error from the existing
`409 llm_not_configured` (lines 77, 116) so the user learns their endpoint is no longer
permitted rather than that they have no config. A dedicated exception type raised by the
service and mapped in the router is the cleanest fit.

## Testing

New `backend/tests/test_url_guard.py`, table-driven:

- Schemes: `file:///etc/passwd`, `ftp://…`, `gopher://…` rejected in every mode.
- Literal addresses rejected in multi-user mode: `127.0.0.1`, `::1`, `10.0.0.1`,
  `192.168.1.1`, `172.16.0.1`, `169.254.169.254`, `fd00:ec2::254`, `0.0.0.0`.
- `http://` rejected in multi-user mode; `https://api.openai.com/v1` allowed.
- Monkeypatched resolver returning a private address for a public-looking hostname →
  rejected. This is the check that makes the guard more than cosmetic.
- Resolver raising → rejected.
- Allowlist origin match → allowed even when it is `http://` and resolves privately.
- `auth_mode = "none"` → `http://127.0.0.1:11434` and `http://localhost:1234/v1` allowed.
- Both the sync and async validators are exercised.

`backend/tests/test_llm_settings.py`: saving a private `base_url` returns 400 in password
mode and succeeds in `none` mode. Existing tests in this file must keep passing — the
default `auth_mode` is `none`, so they should be unaffected.

Note the existing `get_settings()` is `@lru_cache`d (`config.py:55`); tests that vary
`auth_mode` need to clear that cache. Check `test_auth_modes.py` for the established
pattern and reuse it.

## Risk

The request-time re-check means a multi-user instance with an existing `http://` endpoint
stops working until the URL is changed or the operator allowlists it. That is the
intended outcome. On the default `auth_mode=none` nothing changes.

## Out of scope

Pinned-IP transports for LiteLLM (would close the residual resolve-then-connect rebinding
window, at the cost of owning a custom httpx transport); egress restrictions on any other
outbound request path.
