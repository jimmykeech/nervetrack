# Generalize NerveTrack for open-source distribution — design

**Date:** 2026-06-30
**Status:** Approved (brainstorming)

## Problem

NerveTrack today is wired to one operator's instance:

- **Auth is Google-only and invite-only.** The single login path is
  `/api/v1/auth/google/login`, gated by `NERVETRACK_ALLOWED_EMAILS`. With no
  internet or no Google OAuth client there is no way to sign in — local/offline
  use is impossible.
- **The backend container can't run standalone.** `backend/entrypoint.sh` runs
  `litestream replicate`, which fails without S3 credentials, so the image
  requires a Tigris bucket to start.
- **Personal values are hardcoded** across `backend/fly.toml`,
  `frontend/fly.toml`, `.github/workflows/fly-deploy.yml`, and
  `docs/DEPLOY-FLY.md`: app names, `nervetrack.jameskeech.io`, region `syd`,
  timezone `Australia/Sydney`, Friday week-start.
- **No published images and no license**, so "take the container images and
  deploy yourself" is not yet possible, and the code is not legally reusable.

## Goal

Turn this repository into neutral, self-hostable open-source software that
anyone can run **locally with no internet** or **deploy to a cloud provider**
(optionally with Google auth), and extract the current operator's personal
deployment into a separate private repository that consumes published images.

## Decisions (locked during brainstorming)

1. **Auth modes:** `NERVETRACK_AUTH_MODE = none | password | google`, default
   `none`.
2. **Deploy model:** the public repo builds and publishes versioned container
   images to GHCR; the private deploy repo (and other people's deployments)
   consume those images. No source duplication.
3. **Cloud backup (Litestream):** kept in the image but **opt-in** — plain
   `uvicorn` by default (offline-friendly), restore + replicate only when S3 env
   vars are present.
4. **Defaults neutralized:** `timezone = "UTC"`, `week_start_day = 0` (Monday);
   both remain env-configurable.
5. **License:** **AGPL-3.0**.

## Architecture recap (for context)

Two containers: a public **frontend** (SvelteKit/adapter-node) that proxies
`/api/*` to a private **backend** (FastAPI/uvicorn). The backend owns a single
**SQLite file** at `/data/nervetrack.db` on a mounted volume (embedded engine,
WAL mode, one writer, one machine). Migrations in `backend/app/migrations/*.sql`
are applied in order on startup by the runner in `db.py`. In production
Litestream streams the WAL to S3/Tigris for durability/restore. Sessions are
opaque tokens hashed into `auth_sessions`; identity is currently established only
via Google OAuth.

---

## Scope

Items **1–6** below are implemented in *this* repository. Item **7** (the
private deploy repo) is delivered as a documented runbook, since it lives in a
separate repository; it is not executable code in this repo. It may become its
own spec when the operator actually creates that repo.

---

## 1. Pluggable authentication

### Config
- Add to `backend/app/config.py`:
  - `auth_mode: str = "none"` (`none` | `password` | `google`).
  - `allow_registration: bool = True` (gates open password sign-up).
- `google_client_id` / `allowed_emails` etc. remain; they are only consulted in
  `google` mode.

### Auth provider seam (`backend/app/auth.py`)
The shared machinery stays: `create_session` / `delete_session` /
`user_for_token` / `current_user` and the httpOnly session cookie are used by all
modes. Only *identity establishment* differs per mode.

- **`none` (default):** `current_user` resolves to a single canonical local user
  (`email = "local@localhost"`, `google_sub = NULL`), created and seeded on first
  use via a `get_or_create_local_user(db)` helper. No login page; `/auth/me`
  always succeeds. Fully offline. This is what `docker compose up` and a bare
  `uvicorn` give with zero secrets.
- **`password`:** email + password accounts.
  - New deps: `passlib[argon2]` (Argon2 hashing).
  - `POST /api/v1/auth/register` — body `{email, password, name?}`. Allowed only
    when `allow_registration` is true (so a multi-user instance can lock sign-up
    after setup). Creates the user (`password_hash` set, `google_sub = NULL`),
    seeds it, issues a session cookie.
  - `POST /api/v1/auth/login` — body `{email, password}`. Verifies the hash,
    issues a session cookie. Generic error on failure (no user-enumeration).
  - Reuses `_set_session_cookie`, `create_session`, logout.
- **`google`:** existing flow unchanged; its routes are only active when
  `auth_mode == "google"`.

### Public auth-config endpoint
- `GET /api/v1/auth/config` → `{"mode": "none|password|google",
  "allow_registration": bool}`. Public (no session required) so the frontend can
  render the correct screen and the smoke tests can introspect mode.

### Route mounting
`routers/auth.py` registers only the routes relevant to the active mode (Google
routes in `google` mode; register/login in `password` mode; in `none` mode only
`/auth/config`, `/auth/me`, `/auth/logout`). `/auth/me` and `/auth/logout` exist
in all modes.

### Database migration
- `backend/app/migrations/0003_auth_password.sql`: `ALTER TABLE users ADD COLUMN
  password_hash TEXT;` (`google_sub` is already nullable, so `none`/`password`
  users coexist with Google users). No backfill needed.

### Frontend
- `frontend/src/lib/api.ts`: add `authConfig()` → `GET /auth/config`, and
  `register()` / `login()` for password mode.
- `frontend/src/routes/login/+page.svelte`: fetch `/auth/config` and branch:
  - `google` → existing "Sign in with Google" button + invite-only copy.
  - `password` → email/password form (+ a register toggle when
    `allow_registration`).
  - `none` → no login screen is reachable; the layout guard never redirects here
    because `/auth/me` always succeeds. If somehow hit, show a "no login
    required" message and link home.
- The `+layout` route guard logic is unchanged in shape — it still keys off
  `auth/me`. Error-state handling in `auth.svelte.ts` is unchanged.

### Tests
- Backend: `none` mode auto-creates and reuses the single user; `password`
  register/login happy path + wrong password + duplicate email + registration
  disabled; `google` mode unchanged (existing monkeypatched tests still pass);
  per-account isolation still holds across modes; `/auth/config` returns the
  configured mode.
- Frontend: login page renders the correct variant per mode (vitest, mocking
  `authConfig`).

---

## 2. Standalone container — Litestream opt-in

- `backend/entrypoint.sh`: branch on S3 configuration presence (e.g.
  `LITESTREAM_BUCKET` set, falling back to detecting `AWS_*`/`BUCKET_NAME`):
  - **Configured:** `litestream restore -if-db-not-exists -if-replica-exists …`
    then `exec litestream replicate -exec "uvicorn …"` (current behaviour).
  - **Not configured:** `exec uvicorn app.main:app --host :: --port 8000`
    directly — no Litestream, works fully offline.
- `backend/litestream.yml` and the Litestream binary stay in the image; the file
  is only consulted when replication is enabled.
- The published image therefore runs offline out of the box, and any cloud user
  gets durable backup simply by setting the S3 env vars / `fly secrets`.

---

## 3. Neutralized defaults

- `backend/app/config.py`: `timezone = "UTC"`, `week_start_day = 0` (Monday).
- `backend/app/services/seed.py` `SETTINGS_SEED`: `timezone = "UTC"`,
  `week_start_day = "0"`.
- Both remain env/DB configurable. Update any tests/fixtures that assumed the old
  defaults.

---

## 4. Generic repo; deployment specifics extracted

### Removed from this repo (they move to the private deploy repo — see §7)
- `backend/fly.toml`, `frontend/fly.toml` (carry app names / domain / Sydney).
- `.github/workflows/fly-deploy.yml` (deploys the operator's apps, smoke-tests
  `nervetrack.jameskeech.io`).
- `docs/DEPLOY-FLY.md` (operator-specific Fly guide).

### Added — generic, placeholder-only templates
- `deploy/fly/backend.fly.toml.example` and `deploy/fly/frontend.fly.toml.example`
  with `<your-app>` / `<your-domain>` placeholders and comments, so a self-hoster
  can copy and fill them in. No real names or domains.
- `docs/DEPLOY.md` — provider-agnostic deployment guide: durable-storage
  considerations, enabling Litestream backup, and a Google OAuth setup section
  (create a Web client, set the redirect URI to *your* domain), with Fly as a
  worked example. No personal URLs.

### Compose changes
- `docker-compose.yml`: default `NERVETRACK_AUTH_MODE=none`; Google vars become
  optional/commented; backend runs offline with zero secrets.
- `.env.example`: documents every supported variable with neutral defaults
  (replaces reliance on an undocumented personal `.env`).
- `docker-compose.images.yml`: an override that pulls
  `ghcr.io/<owner>/nervetrack-backend:latest` and `-frontend:latest` instead of
  building, for build-free self-hosting.

### License
- Add `LICENSE` containing the **AGPL-3.0** text and update `pyproject.toml` /
  `package.json` license metadata accordingly. Add a short license note to the
  README. (AGPL: anyone running a modified version as a network service must
  offer users its source.)

---

## 5. Publish images to GHCR

- `.github/workflows/release.yml`:
  - Trigger: push of a `v*` tag (plus `workflow_dispatch`).
  - Two jobs (or a matrix) building `backend/` and `frontend/` with
    `docker/build-push-action`, pushing to
    `ghcr.io/<owner>/nervetrack-backend` and `…/nervetrack-frontend`.
  - Tags: the semver (`vX.Y.Z`) and `latest`. Auth via `GITHUB_TOKEN`
    (`packages: write`).
  - Packages set to **public** so anyone can `docker pull` without auth.
- `.github/workflows/ci.yml` is unchanged (ruff + pytest, lint + check + test on
  every PR/push).

---

## 6. Documentation rewrite

- **README.md** reframed as neutral OSS:
  - Three run modes — **local offline** (`none` auth, plain `uvicorn` or compose),
    **Docker**, **cloud** — and the three auth modes with when to use each.
  - Remove `nervetrack.jameskeech.io` and Sydney/Friday framing; present them as
    configurable.
  - Point deployment at `docs/DEPLOY.md`; note images on GHCR and the AGPL
    license.
- **docs/DEPLOY.md** as described in §4.
- Update the existing config table to include `NERVETRACK_AUTH_MODE`,
  `NERVETRACK_ALLOW_REGISTRATION`, and the Litestream/S3 toggle vars.

---

## 7. Operator's private deploy repo (`nervetrack-deploy`) — runbook

Delivered as documentation (in this repo's `docs/DEPLOY.md` or a section of the
README), not as code here.

**Contents of the new private repo:**
- `backend/fly.toml` + `frontend/fly.toml` pinned to a **published image**
  (`flyctl deploy --image ghcr.io/<owner>/nervetrack-backend:vX.Y.Z`), with the
  operator's env overrides: `NERVETRACK_AUTH_MODE=google`,
  `NERVETRACK_TIMEZONE=Australia/Sydney`, `NERVETRACK_WEEK_START_DAY=4`,
  `NERVETRACK_FRONTEND_URL` / `OAUTH_REDIRECT_URI` / `CORS_ORIGINS` for
  `nervetrack.jameskeech.io`, region `syd`.
- Secrets — Google client secret, `NERVETRACK_ALLOWED_EMAILS`, and Litestream
  `AWS_*` / `BUCKET_NAME` — set via `fly secrets`, never committed.
- `.github/workflows/deploy.yml`: `workflow_dispatch` (or triggered on a new
  public release) running `flyctl deploy --image …:<tag>`, using a
  `FLY_API_TOKEN` repo secret.
- A short README documenting the version-bump procedure (pick a released image
  tag, deploy, verify).

**Migration sequence:**
1. Create the private `nervetrack-deploy` repo.
2. Copy the current `backend/fly.toml`, `frontend/fly.toml`, `fly-deploy.yml`,
   and `DEPLOY-FLY.md` into it; repoint the fly configs at GHCR images and move
   secret values into `fly secrets`.
3. Delete those personal files from the public repo (per §4).
4. Cut a public `v*` release to publish the first images (§5).
5. Redeploy the operator's instance from the private repo against that tag.
6. Verify `nervetrack.jameskeech.io` (Google login + data intact, served from the
   image).

---

## Out of scope / YAGNI

- Password reset / email verification flows, rate-limiting, and account
  management UI for `password` mode (note as future; initial password mode is
  register + login only).
- Postgres or any non-SQLite backend.
- Phase 2 Claude chat (already deferred).
- Multi-arch image builds beyond what `docker/build-push-action` does by default
  (can add `linux/arm64` later if requested).

## Risks / notes

- **Auth-mode misconfiguration:** a half-set Google config in `google` mode
  already raises a clear 500 ("Google OAuth is not configured"); keep that. The
  S3-detection in `entrypoint.sh` must be all-or-nothing so a partial S3 config
  doesn't crash an otherwise-offline instance — document the required variable
  set.
- **Default-change churn:** neutralizing timezone/week-start touches seed data
  and a few tests; existing databases keep their stored per-user settings, so
  only *new* accounts get the new defaults.
- **AGPL implications:** documented in the README so deployers understand the
  network-use source-offer obligation.
