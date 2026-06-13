# NerveTrack

A containerised web app for tracking piriformis syndrome / nerve pain recovery —
replacing a spreadsheet workflow with a proper app, plus a server-backed sit/stand
stopwatch for tracking posture time while working.

**Phase 1** (this build): daily tracking, pain events, strengthening sessions,
the timer, history charts, weekly aggregation, and spreadsheet import.
**Phase 2** (designed for, not built): an in-app Claude chat over your data.

## Stack

- **Frontend:** SvelteKit + TypeScript (Svelte 5 runes), Chart.js, plain CSS. Mobile-first.
- **Backend:** FastAPI (Python 3.12+), Pydantic v2, uvicorn.
- **Database:** DuckDB, a single persistent file on a Docker volume. The backend
  is the only process that opens it (DuckDB is single-writer).
- **API:** JSON REST under `/api/v1/`.

## Accounts & login

NerveTrack is **multi-user and invite-only**, with **Google sign-in**. Each account
sees only its own data. Before first run:

1. In **Google Cloud Console → APIs & Services → Credentials**, create an
   **OAuth 2.0 Client ID** of type *Web application*.
2. Add the authorized redirect URI
   `http://localhost:3000/api/v1/auth/google/callback`
   (add the `:5173` variant too if you use the dev compose file).
3. Copy `.env.example` to `.env` and set `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`,
   and `ALLOWED_EMAILS` (comma-separated — only these Google accounts may sign in).

Login flow: the browser hits `/api/v1/auth/google/login` → Google consent → the
backend verifies the identity, checks the invite list, and sets an **httpOnly session
cookie** (opaque token stored in DuckDB). Non-invited accounts are refused. Set
`COOKIE_SECURE=true` when serving over https.

## Running with Docker

Prod-style (frontend on :3000, backend on :8000):

```bash
cp .env.example .env        # set GOOGLE_CLIENT_ID / SECRET / ALLOWED_EMAILS
docker compose up --build
# open http://localhost:3000  → redirected to /login
```

Development with hot reload (Vite dev server on :5173, uvicorn `--reload`):

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build
# open http://localhost:5173
```

The DuckDB file lives on the named volume `nervetrack-data` (`/data/nervetrack.duckdb`),
so data survives container rebuilds. Remove it with `docker compose down -v`.

## Running locally without Docker

Backend:

```bash
cd backend
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
NERVETRACK_DB_PATH=./nervetrack.duckdb .venv/bin/uvicorn app.main:app --reload --port 8000
```

Frontend (proxies `/api` to the backend above):

```bash
cd frontend
npm install
VITE_API_PROXY=http://localhost:8000 npm run dev
# open http://localhost:5173
```

In production the SvelteKit Node server proxies `/api/*` to `BACKEND_URL`
(see `src/hooks.server.ts`); in dev, Vite's proxy handles it.

## Importing the spreadsheet

Open **Settings → Import spreadsheet** and upload the existing
"Piriformis Recovery Tracker" `.xlsx`, or POST it directly:

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
| Exercises | `GET/POST /exercises`, `PATCH /exercises/{id}`, `GET /exercises/{id}/progression` |
| Sessions | `POST /entries/{date}/session`, `PUT /sessions/{id}`, `GET /sessions/{id}/previous`, `GET /sessions/latest` |
| Timer | `POST /timer/start`, `POST /timer/stop`, `GET /timer/current`, `GET /timer/day/{date}`, `PATCH/DELETE /timer/intervals/{id}` |
| Stats & weekly | `GET /stats/daily`, `GET /weeks`, `GET/PUT /weeks/{week_start}` |
| Import / misc | `POST /import/xlsx`, `GET /healthz` |

Interactive docs at `http://localhost:8000/docs` when the backend is running.

### Key behaviours

- **Auth**: every `/api/v1` data route requires a valid session cookie (returns 401
  otherwise); only `/healthz` and the auth endpoints are public. Data is scoped per
  account — entries, timers, sessions, weeks, and the exercise catalogue are all
  per-user, and a new account is seeded with its own catalogue on first login.
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

- **Today** — daily form (G/A/R toggle, steppers, stretch/iced checkboxes, big notes
  field), quick "log a pain jab", inline timer totals, autosave.
- **Timer** — glanceable live display, one-tap posture switching, per-posture totals
  and sit:stand ratio, editable timeline, a 45-minute sitting nudge.
- **History** — entry table with status colours and pain/tingling/posture charts (30/90 days).
- **Exercises** — session form prefilled from the last session, catalogue management,
  per-exercise progression chart.
- **Weekly** — computed metrics alongside editable Key Observations / Overall Status / Trend.

## Tests, lint, format

```bash
# Backend
cd backend && .venv/bin/python -m pytest      # timer, weekly maths, xlsx import, entry upsert
.venv/bin/ruff check app tests

# Frontend
cd frontend && npm test                        # timer/time store logic (vitest)
npm run check                                  # svelte-check types
npm run lint                                   # prettier + eslint
```

## Phase 2 (not built)

The schema and a `get_week_bundle(week_start)` service function are already shaped to
serialise a week's data into an LLM context. `backend/app/routers/ai.py` and the
`ANTHROPIC_API_KEY` env var are reserved for the future in-app chat
(weekly-summary drafting and free-form Q&A over the data). Nothing AI-related runs in Phase 1.
