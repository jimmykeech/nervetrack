# Generalize NerveTrack for OSS Distribution — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make this repository neutral, self-hostable open-source software (local-offline or any-cloud, with optional Google auth) and publish container images, while extracting the operator's personal Fly deployment into a documented private-repo runbook.

**Architecture:** Backend gains a pluggable auth seam (`none` | `password` | `google`) sharing the existing session-cookie machinery; the container entrypoint makes Litestream opt-in so the image runs offline; personal Fly config is replaced by generic templates; a GHCR workflow publishes versioned images.

**Tech Stack:** FastAPI + SQLite (Python 3.12), `passlib[argon2]`; SvelteKit (Svelte 5 runes) + vitest; Docker / docker-compose; GitHub Actions; Fly.io (templates only).

## Global Constraints

- Python `>=3.12`; ruff line-length 100, rules `E,F,I,UP,B,W` (ignore `B008`); `pytest` from `backend/`.
- Frontend Node `22`; `npm run lint` (prettier + eslint), `npm run check`, `npm test` (vitest) must pass.
- License is **AGPL-3.0**; SPDX id `AGPL-3.0-only`.
- Auth config var is `NERVETRACK_AUTH_MODE` ∈ {`none`,`password`,`google`}, default `none`; `NERVETRACK_ALLOW_REGISTRATION` default `true`.
- Neutralized defaults: timezone `UTC`, `week_start_day` `0` (Monday).
- Litestream toggle is the presence of `BUCKET_NAME` (matches `backend/litestream.yml`'s `${BUCKET_NAME}`).
- No new runtime deps in the frontend; backend adds only `passlib[argon2]`.
- All work on branch `feat/oss-generalization`. Commit after every task.

---

## File Structure

**Backend**
- Modify `backend/app/config.py` — add `auth_mode`, `allow_registration`; neutralize TZ/week defaults.
- Modify `backend/app/auth.py` — local-user helper, password hashing/auth, mode-aware `current_user`.
- Create `backend/app/migrations/0003_auth_password.sql` — add `password_hash`.
- Modify `backend/app/routers/auth.py` — mode guards, `/auth/config`, `/auth/register`, `/auth/login`.
- Modify `backend/app/services/seed.py` — neutralize `SETTINGS_SEED`.
- Modify `backend/pyproject.toml` — add `passlib[argon2]`, set license.
- Modify `backend/tests/conftest.py` — autouse cookie-honoring default mode.
- Create `backend/tests/test_auth_modes.py`; modify `backend/tests/test_auth.py`.

**Frontend**
- Modify `frontend/src/lib/api.ts` — `authConfig`, `register`, `login`.
- Modify `frontend/src/routes/login/+page.svelte` — mode-aware UI.
- Create `frontend/src/lib/api.test.ts` — fetch-mocked auth calls.
- Modify `frontend/package.json` — license field.

**Container / deploy / docs**
- Modify `backend/entrypoint.sh` — Litestream opt-in.
- Modify `docker-compose.yml`; create `.env.example`, `docker-compose.images.yml`.
- Create `.github/workflows/release.yml`.
- Remove `backend/fly.toml`, `frontend/fly.toml`, `.github/workflows/fly-deploy.yml`, `docs/DEPLOY-FLY.md`.
- Create `deploy/fly/backend.fly.toml.example`, `deploy/fly/frontend.fly.toml.example`, `docs/DEPLOY.md`.
- Create `LICENSE` (AGPL-3.0); modify `README.md`.

---

## Task 1: Config — auth fields + neutralized defaults

**Files:**
- Modify: `backend/app/config.py`
- Test: `backend/tests/test_auth_modes.py` (create)

**Interfaces:**
- Produces: `Settings.auth_mode: str` (default `"none"`), `Settings.allow_registration: bool` (default `True`); `Settings.timezone` default `"UTC"`, `Settings.week_start_day` default `0`.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_auth_modes.py`:

```python
"""Auth-mode config and behaviour across none/password/google."""

from __future__ import annotations

import pytest

from app.config import Settings, get_settings


def test_config_defaults_are_neutral(monkeypatch):
    # No env: neutral OSS defaults.
    for var in ("NERVETRACK_AUTH_MODE", "NERVETRACK_TIMEZONE", "NERVETRACK_WEEK_START_DAY"):
        monkeypatch.delenv(var, raising=False)
    s = Settings(_env_file=None)
    assert s.auth_mode == "none"
    assert s.allow_registration is True
    assert s.timezone == "UTC"
    assert s.week_start_day == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_auth_modes.py::test_config_defaults_are_neutral -v`
Expected: FAIL (`auth_mode` attribute missing / defaults still Sydney).

- [ ] **Step 3: Implement**

In `backend/app/config.py`, change the timezone/week defaults and add the auth fields:

```python
    # Local timezone used to derive calendar dates from UTC timestamps.
    timezone: str = "UTC"

    # Day the tracking week starts on (0=Monday .. 6=Sunday). Default Monday.
    week_start_day: int = 0
```

Add below `cookie_secure`:

```python
    # Authentication mode: "none" (single local user, offline), "password"
    # (local email+password accounts), or "google" (invite-only Google OAuth).
    auth_mode: str = "none"
    # In password mode, allow open self-service registration. Turn off to lock
    # an instance after the intended accounts exist.
    allow_registration: bool = True
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_auth_modes.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/config.py backend/tests/test_auth_modes.py
git commit -m "feat(config): add auth_mode/allow_registration, neutralize TZ+week defaults"
```

---

## Task 2: Migration + `none` mode single local user

**Files:**
- Create: `backend/app/migrations/0003_auth_password.sql`
- Modify: `backend/app/auth.py`
- Modify: `backend/tests/conftest.py`
- Test: `backend/tests/test_auth_modes.py`

**Interfaces:**
- Produces: `auth.LOCAL_USER_EMAIL = "local@localhost"`; `auth.get_or_create_local_user(db: Database) -> UUID`; `current_user` returns the local user when `auth_mode == "none"` (ignores cookie).
- Consumes: `Settings.auth_mode` (Task 1).

- [ ] **Step 1: Add the cookie-honoring test default (conftest)**

Existing data/isolation tests rely on cookie→user resolution. The new default mode is `none` (cookie-ignoring), so force a cookie-honoring mode for the shared fixtures. Add to `backend/tests/conftest.py` (after imports):

```python
from app.config import get_settings


@pytest.fixture(autouse=True)
def _cookie_auth_mode(monkeypatch):
    # Shared fixtures (auth_client) rely on cookie-based identity; password mode
    # honours the cookie exactly like the old behaviour. none/google tests
    # override this in their own fixtures.
    monkeypatch.setenv("NERVETRACK_AUTH_MODE", "password")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
```

- [ ] **Step 2: Write the failing test (none mode)**

Append to `backend/tests/test_auth_modes.py`:

```python
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture()
def none_mode(monkeypatch):
    monkeypatch.setenv("NERVETRACK_AUTH_MODE", "none")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_none_mode_auto_single_user(db, none_mode):
    c = TestClient(create_app(), raise_server_exceptions=True)
    # No cookie at all, yet /auth/me works and is the local user.
    me = c.get("/api/v1/auth/me")
    assert me.status_code == 200
    assert me.json()["email"] == "local@localhost"
    # Second call resolves the SAME user (no duplicate rows).
    c.get("/api/v1/auth/me")
    rows = db.query("SELECT id FROM users WHERE email = ?", ["local@localhost"])
    assert len(rows) == 1
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_auth_modes.py::test_none_mode_auto_single_user -v`
Expected: FAIL (401 — `none` mode not implemented).

- [ ] **Step 4: Create the migration**

Create `backend/app/migrations/0003_auth_password.sql`:

```sql
-- Local password accounts: hash stored here; NULL for Google/none users.
ALTER TABLE users ADD COLUMN password_hash TEXT;
```

- [ ] **Step 5: Implement the local-user helper + mode-aware current_user**

In `backend/app/auth.py`, add near the top (after `OAUTH_STATE_COOKIE`):

```python
LOCAL_USER_EMAIL = "local@localhost"


def get_or_create_local_user(db: Database) -> UUID:
    """Resolve the single local user (none mode), creating+seeding on first use."""
    existing = db.query_one("SELECT id FROM users WHERE email = ?", [LOCAL_USER_EMAIL])
    if existing:
        return existing["id"]
    created = db.query_one(
        "INSERT INTO users (google_sub, email, name) VALUES (NULL, ?, ?) RETURNING id",
        [LOCAL_USER_EMAIL, "Local"],
    )
    assert created is not None
    seed_user(db, created["id"])
    return created["id"]
```

Replace the body of `current_user` so `none` mode short-circuits:

```python
def current_user(
    session_token: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    db: Database = Depends(db_dep),
) -> UUID:
    """FastAPI dependency: resolve the signed-in user or raise 401."""
    if get_settings().auth_mode == "none":
        return get_or_create_local_user(db)
    if not session_token:
        raise HTTPException(401, "Not authenticated")
    user = user_for_token(db, session_token)
    if user is None:
        raise HTTPException(401, "Session expired or invalid")
    return user["id"]
```

- [ ] **Step 6: Run tests**

Run: `cd backend && python -m pytest tests/test_auth_modes.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add backend/app/migrations/0003_auth_password.sql backend/app/auth.py backend/tests/conftest.py backend/tests/test_auth_modes.py
git commit -m "feat(auth): none-mode single local user + password_hash migration"
```

---

## Task 3: Password hashing + authentication helpers

**Files:**
- Modify: `backend/pyproject.toml`
- Modify: `backend/app/auth.py`
- Test: `backend/tests/test_auth_modes.py`

**Interfaces:**
- Produces: `auth.hash_password(p: str) -> str`; `auth.verify_password(p: str, h: str) -> bool`; `auth.create_password_user(db, email: str, password: str, name: str | None) -> UUID` (raises `ValueError` on duplicate email); `auth.authenticate(db, email: str, password: str) -> UUID | None`.

- [ ] **Step 1: Add the dependency**

In `backend/pyproject.toml`, add to `dependencies`:

```toml
    "passlib[argon2]>=1.7",
```

Install locally: `cd backend && pip install -e ".[dev]"`

- [ ] **Step 2: Write the failing test**

Append to `backend/tests/test_auth_modes.py`:

```python
from app import auth as auth_mod


def test_password_hash_roundtrip():
    h = auth_mod.hash_password("hunter2pass")
    assert h != "hunter2pass"
    assert auth_mod.verify_password("hunter2pass", h) is True
    assert auth_mod.verify_password("wrong", h) is False


def test_create_and_authenticate_password_user(db):
    uid = auth_mod.create_password_user(db, "a@example.com", "hunter2pass", "Ay")
    assert auth_mod.authenticate(db, "a@example.com", "hunter2pass") == uid
    assert auth_mod.authenticate(db, "a@example.com", "nope") is None
    assert auth_mod.authenticate(db, "missing@example.com", "x") is None
    with pytest.raises(ValueError):
        auth_mod.create_password_user(db, "a@example.com", "another", "Dup")
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_auth_modes.py::test_password_hash_roundtrip -v`
Expected: FAIL (`hash_password` undefined).

- [ ] **Step 4: Implement**

In `backend/app/auth.py`, add an import and a module-level context, then the helpers:

```python
from passlib.context import CryptContext

_pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")


def hash_password(password: str) -> str:
    return _pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return _pwd_context.verify(password, password_hash)


def create_password_user(
    db: Database, email: str, password: str, name: str | None
) -> UUID:
    """Create a local password account. Raises ValueError if email exists."""
    if db.query_one("SELECT id FROM users WHERE email = ?", [email]):
        raise ValueError("email already registered")
    created = db.query_one(
        "INSERT INTO users (email, name, password_hash) VALUES (?, ?, ?) RETURNING id",
        [email, name, hash_password(password)],
    )
    assert created is not None
    seed_user(db, created["id"])
    return created["id"]


def authenticate(db: Database, email: str, password: str) -> UUID | None:
    row = db.query_one(
        "SELECT id, password_hash FROM users WHERE email = ?", [email]
    )
    if row is None or not row["password_hash"]:
        return None
    if not verify_password(password, row["password_hash"]):
        return None
    return row["id"]
```

- [ ] **Step 5: Run tests**

Run: `cd backend && python -m pytest tests/test_auth_modes.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/pyproject.toml backend/app/auth.py backend/tests/test_auth_modes.py
git commit -m "feat(auth): argon2 password hashing + create/authenticate helpers"
```

---

## Task 4: Auth routes — `/auth/config`, register/login, mode guards

**Files:**
- Modify: `backend/app/routers/auth.py`
- Modify: `backend/tests/test_auth.py`
- Test: `backend/tests/test_auth_modes.py`

**Interfaces:**
- Produces HTTP: `GET /api/v1/auth/config` → `{"mode", "allow_registration"}` (public); `POST /api/v1/auth/register` (password mode); `POST /api/v1/auth/login` (password mode); Google routes 404 unless `auth_mode == "google"`.
- Consumes: `create_password_user`, `authenticate` (Task 3); `_set_session_cookie`, `create_session` (existing).

- [ ] **Step 1: Update the Google tests for explicit mode (test_auth.py)**

The default test mode is now `password` (Task 2 conftest), so Google tests must opt into `google`. Edit `backend/tests/test_auth.py`:

Change the `oauth_env` fixture to also select Google mode:

```python
@pytest.fixture()
def oauth_env(monkeypatch):
    monkeypatch.setenv("NERVETRACK_AUTH_MODE", "google")
    monkeypatch.setenv("NERVETRACK_ALLOWED_EMAILS", "allowed@example.com")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
```

Update `test_me_requires_auth` to run in Google mode (in `password` mode an absent cookie is still 401, but make the intent explicit) by adding the fixture:

```python
def test_me_requires_auth(client, oauth_env):
    assert client.get("/api/v1/auth/me").status_code == 401
```

- [ ] **Step 2: Write the failing tests (config + password flow)**

Append to `backend/tests/test_auth_modes.py`:

```python
@pytest.fixture()
def password_mode(monkeypatch):
    monkeypatch.setenv("NERVETRACK_AUTH_MODE", "password")
    monkeypatch.setenv("NERVETRACK_ALLOW_REGISTRATION", "true")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_auth_config_reports_mode(db, password_mode):
    c = TestClient(create_app(), raise_server_exceptions=True)
    body = c.get("/api/v1/auth/config").json()
    assert body == {"mode": "password", "allow_registration": True}


def test_register_then_me(db, password_mode):
    c = TestClient(create_app(), raise_server_exceptions=True)
    r = c.post("/api/v1/auth/register", json={"email": "New@Ex.com", "password": "hunter2pass", "name": "N"})
    assert r.status_code == 200
    me = c.get("/api/v1/auth/me")
    assert me.status_code == 200
    assert me.json()["email"] == "new@ex.com"  # normalized lower-case


def test_login_wrong_password_401(db, password_mode):
    c = TestClient(create_app(), raise_server_exceptions=True)
    c.post("/api/v1/auth/register", json={"email": "u@ex.com", "password": "hunter2pass"})
    bad = c.post("/api/v1/auth/login", json={"email": "u@ex.com", "password": "nope"})
    assert bad.status_code == 401


def test_register_duplicate_409(db, password_mode):
    c = TestClient(create_app(), raise_server_exceptions=True)
    c.post("/api/v1/auth/register", json={"email": "u@ex.com", "password": "hunter2pass"})
    dup = c.post("/api/v1/auth/register", json={"email": "u@ex.com", "password": "hunter2pass"})
    assert dup.status_code == 409


def test_register_disabled_403(db, monkeypatch):
    monkeypatch.setenv("NERVETRACK_AUTH_MODE", "password")
    monkeypatch.setenv("NERVETRACK_ALLOW_REGISTRATION", "false")
    get_settings.cache_clear()
    c = TestClient(create_app(), raise_server_exceptions=True)
    r = c.post("/api/v1/auth/register", json={"email": "x@ex.com", "password": "hunter2pass"})
    assert r.status_code == 403
    get_settings.cache_clear()


def test_google_route_404_in_password_mode(db, password_mode):
    c = TestClient(create_app(), raise_server_exceptions=True)
    assert c.get("/api/v1/auth/google/login", follow_redirects=False).status_code == 404
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_auth_modes.py -k "config or register or login or google_route" -v`
Expected: FAIL (routes missing / Google not guarded).

- [ ] **Step 4: Implement the router changes**

In `backend/app/routers/auth.py`:

Add imports:

```python
from pydantic import BaseModel, EmailStr, Field

from app.auth import (
    OAUTH_STATE_COOKIE,
    SESSION_COOKIE,
    authenticate,
    create_password_user,
    create_session,
    current_user,
    delete_session,
    upsert_user,
    verify_google_id_token,
)
```

Add request models and the config + password endpoints (place after `router = APIRouter(...)`):

```python
class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    name: str | None = None


class LoginIn(BaseModel):
    email: EmailStr
    password: str


@router.get("/auth/config")
def auth_config():
    settings = get_settings()
    return {"mode": settings.auth_mode, "allow_registration": settings.allow_registration}


@router.post("/auth/register")
def register(body: RegisterIn, db: Database = Depends(db_dep)):
    settings = get_settings()
    if settings.auth_mode != "password":
        raise HTTPException(404, "Not found")
    if not settings.allow_registration:
        raise HTTPException(403, "Registration is closed")
    try:
        user_id = create_password_user(db, body.email.lower(), body.password, body.name)
    except ValueError:
        raise HTTPException(409, "Email already registered")
    token = create_session(db, user_id)
    resp = JSONResponse({"ok": True})
    _set_session_cookie(resp, token)
    return resp


@router.post("/auth/login")
def login(body: LoginIn, db: Database = Depends(db_dep)):
    if get_settings().auth_mode != "password":
        raise HTTPException(404, "Not found")
    user_id = authenticate(db, body.email.lower(), body.password)
    if user_id is None:
        raise HTTPException(401, "Invalid email or password")
    token = create_session(db, user_id)
    resp = JSONResponse({"ok": True})
    _set_session_cookie(resp, token)
    return resp
```

Guard the two Google routes — add as the first line of `google_login` and `google_callback`:

```python
    if get_settings().auth_mode != "google":
        raise HTTPException(404, "Not found")
```

`EmailStr` requires `email-validator`; add to `backend/pyproject.toml` dependencies:

```toml
    "email-validator>=2.1",
```

Then `cd backend && pip install -e ".[dev]"`.

- [ ] **Step 5: Run the full auth suite**

Run: `cd backend && python -m pytest tests/test_auth.py tests/test_auth_modes.py -v`
Expected: PASS (Google tests still green under explicit `google` mode).

- [ ] **Step 6: Commit**

```bash
git add backend/app/routers/auth.py backend/pyproject.toml backend/tests/test_auth.py backend/tests/test_auth_modes.py
git commit -m "feat(auth): /auth/config + password register/login + google mode guards"
```

---

## Task 5: Neutralize seed defaults

**Files:**
- Modify: `backend/app/services/seed.py`
- Test: `backend/tests/test_auth_modes.py`

**Interfaces:**
- Produces: new accounts seeded with `week_start_day="0"`, `timezone="UTC"`.

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_auth_modes.py`:

```python
def test_seed_defaults_are_neutral(db, user_id):
    rows = db.query(
        "SELECT key, value FROM app_settings WHERE user_id = ?", [user_id]
    )
    settings = {r["key"]: r["value"] for r in rows}
    assert settings["timezone"] == "UTC"
    assert settings["week_start_day"] == "0"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_auth_modes.py::test_seed_defaults_are_neutral -v`
Expected: FAIL (seeded `Australia/Sydney` / `4`).

- [ ] **Step 3: Implement**

In `backend/app/services/seed.py` replace `SETTINGS_SEED`:

```python
# Default app settings. Week start day: 0 = Monday (Mon=0). Neutral defaults;
# operators override via NERVETRACK_* env / per-user settings.
SETTINGS_SEED: dict[str, str] = {
    "week_start_day": "0",
    "timezone": "UTC",
    "sitting_nudge_minutes": "45",
}
```

- [ ] **Step 4: Run the full backend suite**

Run: `cd backend && python -m pytest && ruff check app tests`
Expected: PASS, no lint errors.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/seed.py backend/tests/test_auth_modes.py
git commit -m "feat(seed): neutralize default timezone (UTC) and week start (Monday)"
```

---

## Task 6: Frontend — mode-aware login

**Files:**
- Modify: `frontend/src/lib/api.ts`
- Modify: `frontend/src/routes/login/+page.svelte`
- Create: `frontend/src/lib/api.test.ts`
- Modify: `frontend/package.json`

**Interfaces:**
- Consumes HTTP: `/auth/config`, `/auth/register`, `/auth/login` (Task 4).
- Produces: `api.authConfig()`, `api.register(...)`, `api.login(...)`; `AuthConfig` type.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/lib/api.test.ts`:

```ts
import { afterEach, describe, expect, it, vi } from 'vitest';
import { api } from './api';

afterEach(() => vi.unstubAllGlobals());

function mockFetch(status: number, body: unknown) {
  return vi.fn(async () =>
    new Response(JSON.stringify(body), {
      status,
      headers: { 'Content-Type': 'application/json' }
    })
  );
}

describe('auth api', () => {
  it('authConfig hits /api/v1/auth/config', async () => {
    const f = mockFetch(200, { mode: 'password', allow_registration: true });
    vi.stubGlobal('fetch', f);
    const cfg = await api.authConfig();
    expect(cfg.mode).toBe('password');
    expect(f.mock.calls[0][0]).toBe('/api/v1/auth/config');
  });

  it('login posts credentials', async () => {
    const f = mockFetch(200, { ok: true });
    vi.stubGlobal('fetch', f);
    await api.login('u@ex.com', 'hunter2pass');
    const [url, init] = f.mock.calls[0];
    expect(url).toBe('/api/v1/auth/login');
    expect(init.method).toBe('POST');
    expect(JSON.parse(init.body as string)).toEqual({ email: 'u@ex.com', password: 'hunter2pass' });
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/lib/api.test.ts`
Expected: FAIL (`api.authConfig` undefined).

- [ ] **Step 3: Implement api additions**

In `frontend/src/lib/api.ts`, add the type after `CurrentUser`:

```ts
export interface AuthConfig {
  mode: 'none' | 'password' | 'google';
  allow_registration: boolean;
}
```

Add to the `api` object (in the `// Auth` group):

```ts
  authConfig: () => request<AuthConfig>('/auth/config'),
  register: (email: string, password: string, name?: string) =>
    request<{ ok: boolean }>('/auth/register', {
      method: 'POST',
      body: JSON.stringify({ email, password, name })
    }),
  login: (email: string, password: string) =>
    request<{ ok: boolean }>('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password })
    }),
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npx vitest run src/lib/api.test.ts`
Expected: PASS

- [ ] **Step 5: Implement the mode-aware login page**

Replace `frontend/src/routes/login/+page.svelte` `<script>` and markup (keep the existing `<style>` block; add the small additions noted):

```svelte
<script lang="ts">
  import { onMount } from 'svelte';
  import { page } from '$app/stores';
  import { api, type AuthConfig } from '$lib/api';
  import { goto } from '$app/navigation';

  const errors: Record<string, string> = {
    not_invited: 'That Google account is not on the invite list. Ask the owner to add your email.',
    bad_state: 'Login session expired. Please try again.',
    oauth_failed: 'Google sign-in failed. Please try again.',
    email_unverified: 'Your Google email is not verified.'
  };
  const urlError = $derived($page.url.searchParams.get('error'));

  let cfg = $state<AuthConfig | null>(null);
  let email = $state('');
  let password = $state('');
  let name = $state('');
  let registering = $state(false);
  let formError = $state('');
  let busy = $state(false);

  onMount(async () => {
    cfg = await api.authConfig();
    if (cfg.mode === 'none') goto('/');
  });

  async function submit(e: Event) {
    e.preventDefault();
    busy = true;
    formError = '';
    try {
      if (registering) await api.register(email, password, name || undefined);
      else await api.login(email, password);
      window.location.href = '/';
    } catch (err) {
      formError = registering
        ? 'Could not register. The email may already be in use.'
        : 'Invalid email or password.';
    } finally {
      busy = false;
    }
  }
</script>

<div class="login">
  <div class="card">
    <h1>NerveTrack</h1>
    <p class="muted">Sign in to track your recovery.</p>
    {#if urlError}
      <p class="error">{errors[urlError] ?? 'Sign-in failed. Please try again.'}</p>
    {/if}

    {#if cfg?.mode === 'google'}
      <a class="google" href="/api/v1/auth/google/login">
        <span class="g">G</span> Sign in with Google
      </a>
      <p class="muted small">Access is invite-only.</p>
    {:else if cfg?.mode === 'password'}
      <form onsubmit={submit}>
        {#if formError}<p class="error">{formError}</p>{/if}
        <input type="email" placeholder="Email" bind:value={email} required />
        <input type="password" placeholder="Password" bind:value={password} required minlength="8" />
        {#if registering}
          <input type="text" placeholder="Name (optional)" bind:value={name} />
        {/if}
        <button type="submit" disabled={busy}>{registering ? 'Create account' : 'Sign in'}</button>
        {#if cfg.allow_registration}
          <button type="button" class="link" onclick={() => (registering = !registering)}>
            {registering ? 'Have an account? Sign in' : 'Create an account'}
          </button>
        {/if}
      </form>
    {:else}
      <p class="muted small">Loading…</p>
    {/if}
  </div>
</div>
```

Add to the existing `<style>` block (append before the closing `</style>`):

```css
  form {
    display: flex;
    flex-direction: column;
    gap: 0.6rem;
    margin-top: 1rem;
  }
  input {
    padding: 0.6rem 0.75rem;
    border-radius: 8px;
    border: 1px solid var(--border, #ccc);
    background: var(--surface, #fff);
    color: inherit;
  }
  button[type='submit'] {
    padding: 0.65rem 1rem;
    border-radius: 8px;
    border: none;
    background: var(--accent, #4285f4);
    color: #fff;
    font-weight: 600;
    cursor: pointer;
  }
  button[type='submit']:disabled {
    opacity: 0.6;
  }
  .link {
    background: none;
    border: none;
    color: var(--accent, #4285f4);
    cursor: pointer;
    font-size: 0.9rem;
  }
```

- [ ] **Step 6: Set the license field**

In `frontend/package.json`, add after `"private": true,`:

```json
  "license": "AGPL-3.0-only",
```

- [ ] **Step 7: Run frontend checks**

Run: `cd frontend && npm run lint && npm run check && npm test`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add frontend/src/lib/api.ts frontend/src/lib/api.test.ts frontend/src/routes/login/+page.svelte frontend/package.json
git commit -m "feat(frontend): mode-aware login (google/password/none) + auth api"
```

---

## Task 7: Litestream opt-in entrypoint

**Files:**
- Modify: `backend/entrypoint.sh`

**Interfaces:**
- Produces: container runs plain `uvicorn` unless `BUCKET_NAME` is set, in which case it restores + replicates as before.

- [ ] **Step 1: Replace the entrypoint**

Overwrite `backend/entrypoint.sh`:

```sh
#!/bin/sh
set -e

DB_PATH="${NERVETRACK_DB_PATH:-/data/nervetrack.db}"
SERVE="uvicorn app.main:app --host :: --port 8000"

# Litestream is opt-in: enabled only when an S3 bucket is configured (BUCKET_NAME
# + credentials, as injected by `fly storage create`). Without it the image runs
# uvicorn directly, so it works fully offline / for local self-hosting.
if [ -n "${BUCKET_NAME:-}" ] && [ -n "${AWS_ACCESS_KEY_ID:-}" ]; then
  litestream restore -if-db-not-exists -if-replica-exists -config /etc/litestream.yml "$DB_PATH"
  exec litestream replicate -config /etc/litestream.yml -exec "$SERVE"
fi

exec $SERVE
```

- [ ] **Step 2: Verify offline path works**

Run:
```bash
docker compose build backend
docker compose up -d backend
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8000/healthz
docker compose logs backend | tail -5
docker compose down
```
Expected: `200`; logs show uvicorn started with no Litestream errors.

- [ ] **Step 3: Commit**

```bash
git add backend/entrypoint.sh
git commit -m "feat(container): make Litestream opt-in so the image runs offline"
```

---

## Task 8: Compose defaults + env example + image override

**Files:**
- Modify: `docker-compose.yml`
- Create: `.env.example`
- Create: `docker-compose.images.yml`

- [ ] **Step 1: Default compose to none mode**

In `docker-compose.yml`, under `backend.environment`, change/insert so Google is optional and `none` is the default. Replace the `NERVETRACK_GOOGLE_*` / `ALLOWED_EMAILS` block with:

```yaml
      # Auth mode: none (single local user, no login) | password | google.
      NERVETRACK_AUTH_MODE: ${NERVETRACK_AUTH_MODE:-none}
      NERVETRACK_ALLOW_REGISTRATION: ${NERVETRACK_ALLOW_REGISTRATION:-true}
      # Google OAuth (only used when NERVETRACK_AUTH_MODE=google):
      NERVETRACK_GOOGLE_CLIENT_ID: ${GOOGLE_CLIENT_ID:-}
      NERVETRACK_GOOGLE_CLIENT_SECRET: ${GOOGLE_CLIENT_SECRET:-}
      NERVETRACK_OAUTH_REDIRECT_URI: ${OAUTH_REDIRECT_URI:-http://localhost:3000/api/v1/auth/google/callback}
      NERVETRACK_FRONTEND_URL: ${FRONTEND_URL:-http://localhost:3000}
      NERVETRACK_ALLOWED_EMAILS: ${ALLOWED_EMAILS:-}
```

Also change the timezone default line to neutral:

```yaml
      NERVETRACK_TIMEZONE: ${NERVETRACK_TIMEZONE:-UTC}
```

- [ ] **Step 2: Create `.env.example`**

Create `.env.example` at repo root:

```dotenv
# Copy to .env and adjust. Every value has a working default; the bare
# `docker compose up` runs offline in single-user mode with no secrets.

# Auth: none (default, no login) | password | google
NERVETRACK_AUTH_MODE=none
NERVETRACK_ALLOW_REGISTRATION=true

# Locale
NERVETRACK_TIMEZONE=UTC
NERVETRACK_WEEK_START_DAY=0

# --- Google OAuth (only when NERVETRACK_AUTH_MODE=google) ---
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
ALLOWED_EMAILS=
OAUTH_REDIRECT_URI=http://localhost:3000/api/v1/auth/google/callback
FRONTEND_URL=http://localhost:3000
COOKIE_SECURE=false

# --- Optional cloud backup via Litestream (set all three to enable) ---
# BUCKET_NAME=
# AWS_ACCESS_KEY_ID=
# AWS_SECRET_ACCESS_KEY=
# AWS_ENDPOINT_URL_S3=
# AWS_REGION=auto
```

- [ ] **Step 3: Create the published-image override**

Create `docker-compose.images.yml`:

```yaml
# Run from prebuilt GHCR images instead of building locally:
#   docker compose -f docker-compose.yml -f docker-compose.images.yml up
# Override OWNER/tag as needed.
services:
  backend:
    build: null
    image: ghcr.io/${IMAGE_OWNER:-OWNER}/nervetrack-backend:${IMAGE_TAG:-latest}
  frontend:
    build: null
    image: ghcr.io/${IMAGE_OWNER:-OWNER}/nervetrack-frontend:${IMAGE_TAG:-latest}
```

- [ ] **Step 4: Verify compose config is valid**

Run: `docker compose -f docker-compose.yml -f docker-compose.images.yml config >/dev/null && echo OK`
Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add docker-compose.yml docker-compose.images.yml .env.example
git commit -m "feat(compose): default to offline none mode + .env.example + image override"
```

---

## Task 9: GHCR release workflow

**Files:**
- Create: `.github/workflows/release.yml`

- [ ] **Step 1: Create the workflow**

Create `.github/workflows/release.yml`:

```yaml
name: Release images

# Publishes versioned container images to GHCR on a v* tag (and on demand).
#   git tag v0.2.0 && git push origin v0.2.0
on:
  push:
    tags: ['v*']
  workflow_dispatch: {}

permissions:
  contents: read
  packages: write

jobs:
  images:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        component: [backend, frontend]
    steps:
      - uses: actions/checkout@v4
      - uses: docker/setup-buildx-action@v3
      - uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      - id: meta
        uses: docker/metadata-action@v5
        with:
          images: ghcr.io/${{ github.repository_owner }}/nervetrack-${{ matrix.component }}
          tags: |
            type=semver,pattern={{version}}
            type=raw,value=latest,enable=${{ startsWith(github.ref, 'refs/tags/v') }}
      - uses: docker/build-push-action@v6
        with:
          context: ./${{ matrix.component }}
          push: true
          tags: ${{ steps.meta.outputs.tags }}
          labels: ${{ steps.meta.outputs.labels }}
```

- [ ] **Step 2: Validate YAML**

Run: `python -c "import yaml,sys; yaml.safe_load(open('.github/workflows/release.yml')); print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/release.yml
git commit -m "ci: publish backend+frontend images to GHCR on v* tags"
```

> Note: after the first successful run, set both GHCR packages to **public** in the repo's Packages settings so others can pull without auth. (Manual, one-time — call out in the PR description.)

---

## Task 10: Remove personal deploy files; add generic templates + DEPLOY.md

**Files:**
- Remove: `backend/fly.toml`, `frontend/fly.toml`, `.github/workflows/fly-deploy.yml`, `docs/DEPLOY-FLY.md`
- Create: `deploy/fly/backend.fly.toml.example`, `deploy/fly/frontend.fly.toml.example`, `docs/DEPLOY.md`

- [ ] **Step 1: Remove the operator-specific files**

```bash
git rm backend/fly.toml frontend/fly.toml .github/workflows/fly-deploy.yml docs/DEPLOY-FLY.md
```

- [ ] **Step 2: Create the backend Fly template**

Create `deploy/fly/backend.fly.toml.example`:

```toml
# Copy to your private deploy repo as backend/fly.toml and fill in <...>.
# Private app: no public HTTP service; reachable only from the frontend over the
# 6PN private network. SQLite is single-writer — run exactly ONE machine.
app = "<your-backend-app>"
primary_region = "<region>"

[deploy]
  strategy = "immediate"

# Deploy from a published image instead of building:
#   flyctl deploy --image ghcr.io/<owner>/nervetrack-backend:vX.Y.Z
[build]
  image = "ghcr.io/<owner>/nervetrack-backend:latest"

[env]
  NERVETRACK_DB_PATH = "/data/nervetrack.db"
  NERVETRACK_TIMEZONE = "<Area/City>"
  NERVETRACK_COOKIE_SECURE = "true"
  NERVETRACK_AUTH_MODE = "google"            # or "password"
  NERVETRACK_FRONTEND_URL = "https://<your-domain>"
  NERVETRACK_OAUTH_REDIRECT_URI = "https://<your-domain>/api/v1/auth/google/callback"
  NERVETRACK_CORS_ORIGINS = '["https://<your-domain>"]'
  # Secrets via `fly secrets set`: NERVETRACK_GOOGLE_CLIENT_ID,
  # NERVETRACK_GOOGLE_CLIENT_SECRET, NERVETRACK_ALLOWED_EMAILS, and (for backup)
  # BUCKET_NAME + AWS_* from `fly storage create`.

[mounts]
  source = "nervetrack_data"
  destination = "/data"

[[vm]]
  size = "shared-cpu-1x"
  memory = "512mb"

[checks.health]
  type = "http"
  port = 8000
  method = "get"
  path = "/healthz"
  interval = "15s"
  timeout = "2s"
  grace_period = "30s"
```

- [ ] **Step 3: Create the frontend Fly template**

Create `deploy/fly/frontend.fly.toml.example`:

```toml
# Copy to your private deploy repo as frontend/fly.toml and fill in <...>.
# Public app: serves the UI and proxies /api to the backend over 6PN.
app = "<your-frontend-app>"
primary_region = "<region>"

[build]
  image = "ghcr.io/<owner>/nervetrack-frontend:latest"

[env]
  PORT = "3000"
  BACKEND_URL = "http://<your-backend-app>.internal:8000"

[http_service]
  internal_port = 3000
  force_https = true
  auto_stop_machines = "stop"
  auto_start_machines = true
  min_machines_running = 0

  [[http_service.checks]]
    interval = "15s"
    timeout = "2s"
    grace_period = "5s"
    method = "GET"
    path = "/login"

[[vm]]
  size = "shared-cpu-1x"
  memory = "256mb"
```

- [ ] **Step 4: Create `docs/DEPLOY.md`**

Create `docs/DEPLOY.md`:

```markdown
# Deploying NerveTrack

NerveTrack ships as two container images on GHCR:
`ghcr.io/<owner>/nervetrack-backend` and `…/nervetrack-frontend`. The frontend is
the only public service; it proxies `/api/*` to the private backend, which owns a
single SQLite file on a volume.

## Run anywhere with Docker

```bash
cp .env.example .env        # defaults run offline, single-user
docker compose up           # build locally
# or, from published images:
IMAGE_OWNER=<owner> docker compose -f docker-compose.yml -f docker-compose.images.yml up
```

Open http://localhost:3000.

## Choosing an auth mode

- `NERVETRACK_AUTH_MODE=none` — no login, one local user. Best for a private,
  single-person local/LAN install.
- `NERVETRACK_AUTH_MODE=password` — local email+password accounts. Set
  `NERVETRACK_ALLOW_REGISTRATION=false` after creating your accounts to lock it.
- `NERVETRACK_AUTH_MODE=google` — invite-only Google sign-in (needs internet).

### Google OAuth setup (google mode)

1. Google Cloud Console → APIs & Services → Credentials → create an OAuth 2.0
   Client ID (Web application).
2. Authorized redirect URI: `https://<your-domain>/api/v1/auth/google/callback`.
3. Set `NERVETRACK_GOOGLE_CLIENT_ID`, `NERVETRACK_GOOGLE_CLIENT_SECRET`,
   `NERVETRACK_ALLOWED_EMAILS` (comma-separated invite list),
   `NERVETRACK_OAUTH_REDIRECT_URI`, `NERVETRACK_FRONTEND_URL`,
   `NERVETRACK_CORS_ORIGINS`, and `NERVETRACK_COOKIE_SECURE=true` (https).

## Durable backup (optional, recommended for cloud)

The backend streams the SQLite WAL to any S3-compatible bucket via Litestream
when these are present: `BUCKET_NAME`, `AWS_ACCESS_KEY_ID`,
`AWS_SECRET_ACCESS_KEY`, `AWS_ENDPOINT_URL_S3`, `AWS_REGION`. Unset, the backend
just runs the local file (no backup). On a fresh machine the DB is restored from
the bucket automatically.

## Deploying to Fly.io (worked example)

Templates live in `deploy/fly/`. Copy them, fill in your app names, region, and
domain, then:

```bash
flyctl deploy --config backend/fly.toml --image ghcr.io/<owner>/nervetrack-backend:vX.Y.Z
flyctl deploy --config frontend/fly.toml --image ghcr.io/<owner>/nervetrack-frontend:vX.Y.Z
flyctl secrets set NERVETRACK_GOOGLE_CLIENT_SECRET=... NERVETRACK_ALLOWED_EMAILS=...
```

Run exactly one backend machine (SQLite is single-writer).

## Keeping your deployment in a private repo

Recommended split: keep this public repo generic, and hold your real
`fly.toml`s + secrets in a **private** `nervetrack-deploy` repo that pins a
published image tag. See the runbook in the project README ("Splitting out your
own deployment").
```

- [ ] **Step 5: Verify templates parse and CI still references nothing removed**

Run:
```bash
python -c "import tomllib; tomllib.load(open('deploy/fly/backend.fly.toml.example','rb')); tomllib.load(open('deploy/fly/frontend.fly.toml.example','rb')); print('OK')"
grep -rn "fly-deploy\|DEPLOY-FLY" . --include=*.yml --include=*.md | grep -v docs/superpowers || echo "no stale refs"
```
Expected: `OK`; no stale references (README is updated in Task 12).

- [ ] **Step 6: Commit**

```bash
git add -A deploy docs/DEPLOY.md
git commit -m "docs: remove personal Fly config; add generic deploy templates + DEPLOY.md"
```

---

## Task 11: AGPL license + metadata

**Files:**
- Create: `LICENSE`
- Modify: `backend/pyproject.toml`

- [ ] **Step 1: Add the license file**

Download the canonical AGPL-3.0 text to `LICENSE`:

```bash
curl -fsSL https://www.gnu.org/licenses/agpl-3.0.txt -o LICENSE
head -1 LICENSE
```
Expected first line: `                    GNU AFFERO GENERAL PUBLIC LICENSE`

(If offline, paste the AGPL-3.0 text from https://www.gnu.org/licenses/agpl-3.0.txt manually.)

- [ ] **Step 2: Set backend license metadata**

In `backend/pyproject.toml` `[project]`, add after `description`:

```toml
license = "AGPL-3.0-only"
```

- [ ] **Step 3: Verify**

Run: `head -1 LICENSE && grep license backend/pyproject.toml frontend/package.json`
Expected: AGPL header line; both files show `AGPL-3.0-only`.

- [ ] **Step 4: Commit**

```bash
git add LICENSE backend/pyproject.toml
git commit -m "chore: add AGPL-3.0 license + package metadata"
```

---

## Task 12: README rewrite + private-deploy runbook

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Reframe the intro, Accounts, and Deployment sections**

Edit `README.md`:

Replace the **Accounts & login** section (lines describing Google-only invite) with a mode summary:

```markdown
## Accounts & login

NerveTrack supports three auth modes via `NERVETRACK_AUTH_MODE`:

- **`none`** (default) — no login; a single local user. Ideal for a private
  local/LAN install with no internet.
- **`password`** — local email+password accounts. Open registration by default
  (`NERVETRACK_ALLOW_REGISTRATION`); lock it once your accounts exist.
- **`google`** — invite-only Google sign-in (`NERVETRACK_ALLOWED_EMAILS`).
  Requires a Google OAuth Web client and internet access.

Each account sees only its own data. See [docs/DEPLOY.md](docs/DEPLOY.md) for
Google OAuth setup and cloud deployment.
```

In the **Configuration** table, add rows for `NERVETRACK_AUTH_MODE`
(`none`), `NERVETRACK_ALLOW_REGISTRATION` (`true`), update `NERVETRACK_TIMEZONE`
default to `UTC` and `NERVETRACK_WEEK_START_DAY` to `0` (Monday), and add the
optional Litestream block (`BUCKET_NAME`, `AWS_*`).

Replace the **Deployment** section body with:

```markdown
## Deployment

Container images are published to GHCR on every `v*` tag
(`ghcr.io/<owner>/nervetrack-backend` and `…-frontend`). Run them locally with
Docker, or deploy to any cloud. Full instructions — auth modes, Google OAuth,
optional Litestream backup, and a Fly.io worked example — are in
**[docs/DEPLOY.md](docs/DEPLOY.md)**. Deploy templates live in `deploy/fly/`.

### Splitting out your own deployment

Keep this repo generic and put your real deployment in a **private**
`nervetrack-deploy` repo that consumes the published images:

1. Create the private repo; copy `deploy/fly/*.example` to `backend/fly.toml` /
   `frontend/fly.toml` and fill in your app names, region, and domain.
2. Pin an image tag (`flyctl deploy --image ghcr.io/<owner>/nervetrack-backend:vX.Y.Z`).
3. Put secrets in `fly secrets` (Google client secret, `ALLOWED_EMAILS`, and
   `BUCKET_NAME` + `AWS_*` for backup) — never in git.
4. Add a `deploy.yml` workflow (`workflow_dispatch`) that runs `flyctl deploy
   --image …:<tag>` with a `FLY_API_TOKEN` secret.
5. To upgrade: bump the image tag to a new release and redeploy.
```

Remove every `nervetrack.jameskeech.io` reference and the License-less framing;
add a one-line license note: `NerveTrack is licensed under **AGPL-3.0** (see
[LICENSE](LICENSE)).`

- [ ] **Step 2: Verify no personal references remain**

Run: `grep -rn "jameskeech" README.md docs/DEPLOY.md deploy/ || echo "clean"`
Expected: `clean`

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: reframe README as neutral OSS + private-deploy runbook"
```

---

## Final verification

- [ ] **Backend:** `cd backend && python -m pytest && ruff check app tests` → all pass.
- [ ] **Frontend:** `cd frontend && npm run lint && npm run check && npm test` → all pass.
- [ ] **Offline smoke:** `docker compose up --build` with no `.env`; open http://localhost:3000 → app loads with no login (none mode), data persists.
- [ ] **Workflows valid:** `python -c "import yaml; yaml.safe_load(open('.github/workflows/release.yml')); yaml.safe_load(open('.github/workflows/ci.yml')); print('OK')"`.
- [ ] **No stale personal refs:** `grep -rn "jameskeech\|fly-deploy\|DEPLOY-FLY" --include=*.md --include=*.yml --include=*.toml . | grep -v docs/superpowers` → empty.
- [ ] Open a PR from `feat/oss-generalization`; in the description note the one-time manual step to set GHCR packages public after the first release run.

---

## Self-review notes (author)

- **Spec coverage:** §1 auth → Tasks 1–4,6; §2 Litestream → Task 7; §3 defaults → Tasks 1,5; §4 generic repo/templates/license → Tasks 8,10,11; §5 GHCR → Task 9; §6 docs → Tasks 10,12; §7 runbook → Tasks 10,12. All covered.
- **Type consistency:** `auth_mode`/`allow_registration`, `get_or_create_local_user`, `create_password_user`, `authenticate`, `hash_password`/`verify_password`, `AuthConfig`, `api.authConfig/register/login` used consistently across tasks.
- **Test-default risk handled:** conftest autouse sets `password` (cookie-honoring) so existing data/isolation tests are unaffected by the new `none` default; Google tests opt into `google` explicitly.
```
