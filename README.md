# NerveTrack

A containerised web app for tracking piriformis syndrome / nerve pain recovery —
replacing a spreadsheet workflow with a proper app, plus a server-backed sit/stand
stopwatch for tracking posture time while working.

**Phase 1** (this build): daily tracking, a timestamped note log, pain events,
strengthening sessions, the posture timer, a per-day event timeline, history charts,
weekly aggregation, and spreadsheet import.
**Phase 2** (designed for, not built): an in-app Claude chat over your data.

## Stack

- **Frontend:** SvelteKit + TypeScript (Svelte 5 runes), Chart.js, plain CSS. Mobile-first.
- **Backend:** FastAPI (Python 3.12+), Pydantic v2, uvicorn.
- **Database:** SQLite in WAL mode, a single file on a persistent volume. The backend
  owns the file; `backend/app/migrations/*.sql` are applied in order on startup by a
  tiny built-in migration runner. In production the WAL is streamed off-box
  continuously by [Litestream](https://litestream.io) to an S3 bucket (see
  [Deployment](#deployment)).
- **API:** JSON REST under `/api/v1/`.

## Accounts & login

NerveTrack is **multi-user and invite-only**, with **Google sign-in**. Each account
sees only its own data. Before first run:

1. In **Google Cloud Console → APIs & Services → Credentials**, create an
   **OAuth 2.0 Client ID** of type *Web application*.
2. Add the authorized redirect URI
   `http://localhost:3000/api/v1/auth/google/callback`
   (add the `:5173` variant too if you use the dev compose file).
3. Create a `.env` in the repo root (see [Configuration](#configuration)) and set at
   least `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, and `ALLOWED_EMAILS`
   (comma-separated — only these Google accounts may sign in).

Login flow: the browser hits `/api/v1/auth/google/login` → Google consent → the
backend verifies the identity, checks the invite list, and sets an **httpOnly session
cookie** (opaque token stored in the database). Non-invited accounts are refused. Set
`COOKIE_SECURE=true` when serving over https.

## Configuration

Backend settings are read from the environment with the `NERVETRACK_` prefix
(see `backend/app/config.py`). For Docker, put the **unprefixed** names below in a
`.env` at the repo root — `docker-compose.yml` maps them onto the prefixed container
vars. No `.env` is committed (it holds secrets); create your own.

| `.env` key (Docker) | Backend var | Default | Purpose |
|---|---|---|---|
| `GOOGLE_CLIENT_ID` | `NERVETRACK_GOOGLE_CLIENT_ID` | — | Google Web OAuth client id |
| `GOOGLE_CLIENT_SECRET` | `NERVETRACK_GOOGLE_CLIENT_SECRET` | — | Google Web OAuth client secret |
| `ALLOWED_EMAILS` | `NERVETRACK_ALLOWED_EMAILS` | — | Comma-separated invite list (empty = nobody) |
| `OAUTH_REDIRECT_URI` | `NERVETRACK_OAUTH_REDIRECT_URI` | `http://localhost:3000/api/v1/auth/google/callback` | Must match the Google console redirect URI |
| `FRONTEND_URL` | `NERVETRACK_FRONTEND_URL` | `http://localhost:3000` | Where to send the browser after login |
| `SESSION_TTL_DAYS` | `NERVETRACK_SESSION_TTL_DAYS` | `30` | Session cookie lifetime |
| `COOKIE_SECURE` | `NERVETRACK_COOKIE_SECURE` | `false` | Mark the session cookie `Secure` (set `true` over https) |
| `NERVETRACK_TIMEZONE` | `NERVETRACK_TIMEZONE` | `Australia/Sydney` | Timezone used to derive calendar dates from UTC |
| `NERVETRACK_DB_PATH` | `NERVETRACK_DB_PATH` | `/data/nervetrack.db` | SQLite file path |
| `NERVETRACK_WEEK_START_DAY` | `NERVETRACK_WEEK_START_DAY` | `4` (Friday) | Day the tracking week starts (0=Mon..6=Sun) |
| `BACKEND_URL` | — | `http://backend:8000` | Frontend (prod Node server) → backend base URL |
| `VITE_API_PROXY` | — | `http://localhost:8000` | Frontend (dev Vite proxy) → backend base URL |
| `ANTHROPIC_API_KEY` | `NERVETRACK_ANTHROPIC_API_KEY` | — | Reserved for Phase 2; unused in Phase 1 |

> Running the backend **locally without Docker** loads `backend/.env` via
> pydantic-settings, which expects the **prefixed** names directly (e.g.
> `NERVETRACK_GOOGLE_CLIENT_ID`), or pass them inline as shown below.

## Running with Docker

Prod-style (frontend on :3000, backend on :8000):

```bash
# create .env with GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET / ALLOWED_EMAILS (see Configuration)
docker compose up --build
# open http://localhost:3000  → redirected to /login
```

Development with hot reload (Vite dev server on :5173, uvicorn `--reload`):

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build
# open http://localhost:5173
```

The SQLite file lives on the named volume `nervetrack-data` (`/data/nervetrack.db`),
so data survives container rebuilds. Remove it with `docker compose down -v`.

## Running locally without Docker

Backend:

```bash
cd backend
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
NERVETRACK_DB_PATH=./nervetrack.db .venv/bin/uvicorn app.main:app --reload --port 8000
```

Frontend (proxies `/api` to the backend above):

```bash
cd frontend
npm install
VITE_API_PROXY=http://localhost:8000 npm run dev
# open http://localhost:5173
```

In production the SvelteKit Node server proxies `/api/*` to `BACKEND_URL`
(see `frontend/src/hooks.server.ts`); in dev, Vite's proxy handles it
(`frontend/vite.config.ts`).

## Importing the spreadsheet

Open **Settings → Import spreadsheet** and upload the existing
"Piriformis Recovery Tracker" `.xlsx`, or POST it directly (auth required):

```bash
curl -F "file=@tracker.xlsx" http://localhost:8000/api/v1/import/xlsx
```

It imports three sheets — **Daily Tracker**, **Exercise Log**, **Weekly Summary** —
and is tolerant of messy values (`-`, blanks, `Yes - Many`, `4hrs`/`30min` durations,
forward-filled session dates). Import is **idempotent**: re-running matches on date
(and date+exercise) without duplicating. Computed weekly metrics are recalculated
from the daily data; only the user-written weekly fields are imported.

## API overview (`/api/v1`)

| Area | Endpoints |
|---|---|
| Auth | `GET /auth/google/login`, `GET /auth/google/callback`, `POST /auth/logout`, `GET /auth/me` |
| Daily entries | `GET /entries`, `GET/PUT /entries/{date}`, `POST /entries/{date}/pain-events`, `DELETE /pain-events/{id}` |
| Notes | `POST /entries/{date}/notes`, `PATCH /notes/{id}`, `DELETE /notes/{id}` |
| Exercises | `GET/POST /exercises`, `PATCH /exercises/{id}`, `GET /exercises/{id}/progression` |
| Sessions | `POST /entries/{date}/session`, `PUT /sessions/{id}`, `GET /sessions/{id}/previous`, `GET /sessions/latest` |
| Timer | `POST /timer/start`, `POST /timer/stop`, `GET /timer/current`, `GET /timer/day/{date}`, `PATCH/DELETE /timer/intervals/{id}` |
| Stats & weekly | `GET /stats/daily`, `GET /weeks`, `GET/PUT /weeks/{week_start}` |
| Import / misc | `POST /import/xlsx`, `GET /ai/status` (Phase 2 placeholder), `GET /healthz` |

Interactive docs at `http://localhost:8000/docs` when the backend is running.

### Key behaviours

- **Auth**: every `/api/v1` data route requires a valid session cookie (returns 401
  otherwise); only `/healthz`, `/ai/status`, and the auth endpoints are public. Data is
  scoped per account — entries, notes, timers, sessions, weeks, and the exercise
  catalogue are all per-user, and a new account is seeded with its own catalogue on
  first login.
- **Notes & timeline**: notes are a timestamped log (not a single text field). Each
  day's timeline merges timer intervals, pain jabs, completed checkboxes, and notes
  into one chronological list (newest first).
- **Timer**: one interval runs at a time. `POST /timer/start` stops any running
  interval and starts the new posture immediately (tapping *Standing* while sitting
  is a single action). The running interval lives server-side, so closing the tab
  doesn't lose it — the UI restores it via `GET /timer/current`.
- **Time**: all timestamps are stored in UTC; calendar dates are derived in the
  configured timezone (`NERVETRACK_TIMEZONE`, default `Australia/Sydney`), so a
  23:00 sitting interval lands on the correct local day.
- **Weeks**: tracking weeks run Friday→Thursday by default (`NERVETRACK_WEEK_START_DAY`).
  Suggested overall status: R if any red day, A if ≥3 amber days, else G.

## Pages

**Today · Timer · History · Exercises · Weekly · Settings**

- **Today** — daily form (G/A/R toggle, steppers, stretch/iced checkboxes), quick
  "log a pain jab", a note composer, a chronological day timeline, inline timer
  totals, autosave. The timeline shows the 10 most recent events with a *Show all*
  toggle, and surfaces any text attached to an entry (timer-interval labels, pain
  context, note bodies).
- **Timer** — glanceable live display, one-tap posture switching, per-posture totals
  and sit:stand ratio, editable timeline, a 45-minute sitting nudge.
- **History** — entry table with status colours and pain/tingling/posture charts (30/90 days).
- **Exercises** — session form prefilled from the last session, catalogue management,
  per-exercise progression chart.
- **Weekly** — computed metrics alongside editable Key Observations / Overall Status / Trend.

## Tests, lint, format

```bash
# Backend  (pytest covers auth, per-account isolation, db type round-trips,
#           entry upsert, timer, weekly maths, and xlsx import)
cd backend && .venv/bin/python -m pytest
.venv/bin/ruff check app tests

# Frontend
cd frontend && npm test                        # vitest — timeline, time, posture, ratio, theme
npm run check                                  # svelte-check types
npm run lint                                   # prettier + eslint
```

CI (`.github/workflows/ci.yml`) runs the backend and frontend suites on every PR and
push to `main`.

## Deployment

NerveTrack deploys to [Fly.io](https://fly.io) as two apps — a **private** backend
(FastAPI + SQLite on a volume) and a **public** frontend (SvelteKit, proxies `/api`
to the backend over Fly's private network). The SQLite WAL is replicated continuously
to a [Tigris](https://www.tigrisdata.com) S3 bucket via Litestream
(`backend/litestream.yml`, `backend/entrypoint.sh`), and restored on a fresh machine.
Deploys are tag-triggered (`git tag v* && git push --tags`) via
`.github/workflows/fly-deploy.yml`.

Full instructions — app creation, volume, secrets, OAuth redirect, custom domain,
rollback, and backups — are in **[docs/DEPLOY-FLY.md](docs/DEPLOY-FLY.md)**.

## Phase 2 (not built)

The schema and a `get_week_bundle(week_start)` service function are already shaped to
serialise a week's data into an LLM context. `backend/app/routers/ai.py` (currently a
`GET /ai/status` placeholder returning `coming_soon`) and the `ANTHROPIC_API_KEY` env
var are reserved for the future in-app chat (weekly-summary drafting and free-form
Q&A over the data). Nothing AI-related runs in Phase 1.
