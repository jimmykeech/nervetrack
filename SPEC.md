# NerveTrack — Project Specification

A containerised web application for tracking piriformis syndrome / nerve pain recovery. This replaces a spreadsheet-based tracking workflow ("Piriformis Recovery Tracker") with a proper web app, and adds a sit/stand stopwatch for tracking posture time while working.

Read this entire document before writing any code. Build **Phase 1 only** (tracking + timer). Phase 2 (AI analysis) is documented so the schema and architecture accommodate it, but do not implement it yet.

---

## 1. Tech Stack & Architecture

- **Monorepo** with a `frontend` and `backend` app, plus shared infra config at the root.
- **Frontend:** Svelte (use SvelteKit) + TypeScript. Keep styling simple — plain CSS or a lightweight utility approach. Must work well on both desktop and mobile (data entry often happens from a phone).
- **Backend:** FastAPI (Python 3.12+), Pydantic v2 models, served with uvicorn.
- **Database:** DuckDB, stored as a single persistent file (e.g. `/data/nervetrack.duckdb`) on a Docker volume. The backend is the only process that opens the DB file (DuckDB is single-writer — do not share the file between containers).
- **Containerisation:** Dockerfile per app + a root `docker-compose.yml`. One compose command brings the whole stack up.
- **API style:** JSON REST under `/api/v1/`. Frontend talks to the backend via this API only.

### Repository layout

```
nervetrack/
├── docker-compose.yml
├── README.md
├── .env.example
├── backend/
│   ├── Dockerfile
│   ├── pyproject.toml
│   ├── app/
│   │   ├── main.py            # FastAPI app factory, CORS, router mounting
│   │   ├── db.py              # DuckDB connection management + migrations
│   │   ├── models/            # Pydantic schemas
│   │   ├── routers/           # daily_entries, exercises, sessions, timer, weekly, import
│   │   └── services/          # business logic (weekly aggregation, timer calcs, xlsx import)
│   └── tests/
└── frontend/
    ├── Dockerfile
    ├── package.json
    └── src/
        ├── routes/            # SvelteKit pages
        └── lib/               # API client, components, stores
```

### docker-compose requirements

- `backend` service: builds from `backend/`, exposes port 8000, mounts a named volume `nervetrack-data` at `/data` for the DuckDB file.
- `frontend` service: builds from `frontend/`, exposes port 3000 (or 5173 in dev), proxies `/api` to the backend.
- Support a dev mode with hot reload (bind-mount source, `--reload` for uvicorn, `vite dev` for the frontend). A simple approach: `docker-compose.yml` for prod-style and `docker-compose.dev.yml` override for development.
- `.env.example` documenting any config (ports, DB path, and a placeholder `ANTHROPIC_API_KEY` for Phase 2 — unused for now).

---

## 2. Domain Background (context for design decisions)

The user is recovering from piriformis-related nerve pain (sciatic irritation, left side). Daily tracking captures symptoms, activity, and a structured strengthening program. Key concepts:

- **Status (G/A/R):** Green = continue as planned, Amber = reduce intensity, Red = pause strengthening / see physio. Assigned per day.
- **Sharp pain episodes:** discrete jabs of nerve pain, counted per day, each with a severity (the day records the count and the *worst* pain level 0–10, allowing half points like 2.5).
- **Tingling:** chronic nerve irritation, tracked as a daily level (0–10) and an approximate duration (e.g. "2hrs").
- **Strengthening sessions:** done roughly every other day, with a session-level intensity rating (1–10, half points allowed) and a per-exercise log (sets, reps, weight, difficulty 1–10, nerve response, modifications). Exercises progress over time (new exercises added, reps/weight increased, exercises retired).
- **Sitting vs standing** is the single biggest symptom driver — prolonged sitting aggravates the nerve. This is why the timer feature matters.
- Free-text daily notes are rich and heavily used (timestamps of pain events, activities, what helped). Notes must be a first-class, generously sized field.

---

## 3. Data Model (DuckDB schema)

Use sequences or UUIDs for primary keys (DuckDB supports both; UUID via `gen_random_uuid()` is fine). Create a tiny migration runner in `db.py`: a `schema_migrations` table and ordered SQL migration files applied at startup.

### `daily_entries`

One row per calendar date.

| column | type | notes |
|---|---|---|
| id | UUID PK | |
| entry_date | DATE UNIQUE NOT NULL | |
| status | TEXT CHECK in ('G','A','R') | nullable until user sets it |
| strengthening_done | BOOLEAN | |
| session_intensity | DECIMAL(3,1) | 1–10, nullable, half points allowed |
| sharp_pain_episodes | INTEGER | count, default 0 |
| worst_pain | DECIMAL(3,1) | 0–10, nullable |
| tingling_level | DECIMAL(3,1) | 0–10, nullable |
| tingling_duration_minutes | INTEGER | nullable (UI lets user enter "2hrs", "30min" — store minutes) |
| stretches_morning | BOOLEAN | the spreadsheet had one "Stretches Done?" column but notes always distinguish morning vs nightly routines — split it |
| stretches_night | BOOLEAN | |
| sitting_breaks | TEXT | free text, e.g. "Yes - Many", "A few" (spreadsheet values are unstructured; keep text but also see `sit_stand_sessions` which will supersede this) |
| sleep_quality | DECIMAL(2,1) | 1–5, half points allowed |
| iced | BOOLEAN | icing the piriformis appears constantly in notes — promote to a field |
| notes | TEXT | long free text |
| created_at / updated_at | TIMESTAMP | |

### `pain_events` (optional but recommended)

The notes show the user records individual pain jabs with times ("sharp pain at 3:30pm, level 3"). Give this structure:

| column | type |
|---|---|
| id | UUID PK |
| daily_entry_id | FK → daily_entries |
| occurred_at | TIMESTAMP |
| pain_level | DECIMAL(3,1) |
| context | TEXT (e.g. "sitting at desk", "during stretch") |

`daily_entries.sharp_pain_episodes` and `worst_pain` should be derivable from these when events exist, but keep the summary columns editable directly too (user may just log totals).

### `exercises` (catalogue)

| column | type |
|---|---|
| id | UUID PK |
| name | TEXT UNIQUE (e.g. "Glute Bridges", "Goblet Squats", "Dead Bug") |
| active | BOOLEAN (retired exercises like Forearm Plank get deactivated, history retained) |
| sort_order | INTEGER |

Seed with the exercises from the spreadsheet: Glute Bridges, Clamshells, Side-Lying Hip Abduction, Standing Hip Hinge, Goblet Squats, Step-Ups, Dead Bug, Bird Dog, Dumbbell Rows, Forearm Plank, Side Plank, Hollowbody Hold, Pelvic Tilts, Dumbbell Curls.

### `strength_sessions` and `exercise_logs`

```
strength_sessions: id, daily_entry_id FK, performed_at TIMESTAMP,
                   intensity DECIMAL(3,1), notes TEXT

exercise_logs: id, session_id FK, exercise_id FK,
               sets INTEGER, reps INTEGER,
               hold_seconds INTEGER (nullable — planks/hollowbody use time not reps),
               weight_kg DECIMAL(4,1) (nullable),
               difficulty DECIMAL(3,1) (1–10),
               nerve_response TEXT (nullable, e.g. "slight twinge during 2nd set"),
               modification TEXT (nullable, e.g. "heel elevation with mat")
```

### `sit_stand_sessions` (timer data)

| column | type | notes |
|---|---|---|
| id | UUID PK | |
| entry_date | DATE NOT NULL | which day this belongs to |
| posture | TEXT CHECK in ('sitting','standing','lying','walking') | sitting and standing are primary; lying/walking included because the notes use them constantly ("went and lied down for 20mins") |
| started_at | TIMESTAMP NOT NULL | |
| ended_at | TIMESTAMP | NULL while running |
| duration_seconds | INTEGER | computed on stop; stored for fast aggregation |
| label | TEXT nullable | e.g. "work", "meeting" |

### `weekly_summaries`

The spreadsheet has rich hand-written weekly summaries. Phase 1: auto-compute the numeric parts, let the user write the qualitative parts.

| column | type | notes |
|---|---|---|
| id | UUID PK | |
| week_start | DATE UNIQUE (the Friday — the user's tracking weeks run Fri→Thu; make week start day configurable in settings, default Friday) |
| strengthening_sessions | INTEGER | computed |
| avg_pain_episodes_per_day | DECIMAL | computed |
| avg_tingling_level | DECIMAL | computed |
| worst_pain | DECIMAL | computed |
| overall_status | TEXT (G/A/R) | user-set, with a suggested default (R if any R day, A if ≥3 amber days, else G) |
| key_observations | TEXT | user-written (Phase 2 will offer AI drafting) |
| trend_vs_last_week | TEXT | user-set: Better / Same / Slightly Worse / Worse |

### `app_settings`

Simple key/value table (week start day, timezone — default `Australia/Sydney`-style local handling; all timestamps stored UTC, dates derived in the user's timezone).

---

## 4. API Endpoints (FastAPI, `/api/v1`)

**Daily entries**
- `GET /entries?from=&to=` — list (summary fields)
- `GET /entries/{date}` — full entry incl. pain events, session + exercise logs, sit/stand totals
- `PUT /entries/{date}` — upsert (create-or-update by date; this is the primary write path)
- `POST /entries/{date}/pain-events` / `DELETE /pain-events/{id}`

**Exercise & sessions**
- `GET /exercises` / `POST /exercises` / `PATCH /exercises/{id}` (rename, activate/deactivate, reorder)
- `POST /entries/{date}/session` — create session with nested exercise logs
- `PUT /sessions/{id}` — update session + logs
- `GET /sessions/{id}/previous` — returns the most recent prior session's logs (used to prefill the form: "same as last time" is the dominant workflow, with occasional progressions)

**Timer**
- `POST /timer/start` `{posture, label?}` — stops any currently running interval (postures are mutually exclusive) and starts a new one; returns the running interval
- `POST /timer/stop` — ends the running interval
- `GET /timer/current` — running interval, if any (used to restore state on page load)
- `GET /timer/day/{date}` — all intervals for a day + per-posture totals
- `PATCH /timer/intervals/{id}` / `DELETE /timer/intervals/{id}` — manual corrections

**Stats & weekly**
- `GET /stats/daily?from=&to=` — time series for charts (pain episodes, worst pain, tingling, intensity, sit/stand minutes per day)
- `GET /weeks` / `GET /weeks/{week_start}` — computed metrics merged with user-written fields
- `PUT /weeks/{week_start}` — save user-written fields

**Import**
- `POST /import/xlsx` — accepts the existing spreadsheet and imports all three sheets (see §6)

**Misc**
- `GET /healthz`

Validation: enforce ranges (pain/tingling 0–10, intensity 1–10, sleep 1–5, status in G/A/R) in Pydantic. Return helpful 422s.

---

## 5. Frontend Pages & UX

Keep the UI clean and fast. Navigation: **Today · Timer · History · Exercises · Weekly**.

### Today (default page)
- Date selector (defaults to today, easy to flip to yesterday — entries are often completed the next morning).
- The daily entry form mirroring the spreadsheet columns: status as a three-button G/A/R toggle (green/amber/red colours), steppers/sliders for the numeric ratings, checkboxes for morning/night stretches and icing, a large auto-growing notes textarea.
- Quick "log a pain jab" button: one tap opens a mini-form (level + optional context, time defaults to now) and increments the day's episode count.
- Inline summary of today's timer totals (e.g. "Sitting 3h 12m · Standing 1h 40m").
- Autosave on change (debounced PUT), with a subtle saved indicator.

### Timer (the stopwatch feature)
- Big, glanceable display: current posture, live elapsed time for the current interval, and today's running totals per posture (sitting / standing / lying / walking) plus a sit:stand ratio.
- One-tap posture buttons: tapping **Standing** while sitting ends the sitting interval and starts standing immediately (no separate stop step). A **Stop** button ends tracking without starting a new posture.
- The running interval lives server-side, so closing the tab/phone doesn't lose it; on load, `GET /timer/current` restores the live state.
- A timeline list of today's intervals with edit/delete for corrections (forgot to switch, etc.).
- Optional nicety: a configurable "you've been sitting for 45 min" visual nudge.

### History
- Table/list of past entries with the key columns and status colour-coding; click through to a day's full detail.
- Simple charts (last 30/90 days): pain episodes per day, tingling level, worst pain, session intensity overlay, and daily sitting vs standing minutes. Use a lightweight chart lib (e.g. Chart.js or layerchart) — nothing heavy.

### Exercises
- Session entry form for a chosen date: prefilled from the previous session (`/sessions/{id}/previous`), per-exercise rows with sets / reps / hold seconds / weight / difficulty / nerve response / modification. Adding or removing exercises from the catalogue.
- Per-exercise progression view: difficulty and load over time for one exercise.

### Weekly
- List of weeks with computed metrics and trend badges; a week detail page showing computed numbers alongside editable Key Observations / Overall Status / Trend fields.

---

## 6. Spreadsheet Import

Implement `POST /import/xlsx` so existing history isn't lost. The source workbook has three sheets:

1. **Daily Tracker** — header on row 3. Columns: Date (Excel serial number — convert properly), Day, Status (G/A/R), Strengthening Session? (Yes/No), Session Intensity (1–10 or "-"), Sharp Pain Episodes, Worst Pain (number or "-"), Tingling Level, Tingling Duration (free text like "4hrs", "30min", "1.5hr" — parse to minutes, keep raw string in notes if unparseable), Stretches Done? (Yes/No → set both morning and night true), Sitting Breaks Taken? (free text), Sleep Quality (1–5), Notes.
2. **Weekly Summary** — header row with: Week, Date Range ("06/03/2026 - 12/03/2026", DD/MM/YYYY), Strengthening Sessions, Avg Pain Episodes/Day, Avg Tingling Level, Worst Pain Day, Overall Status, Exercises Completed, Pigeon Pose Progress?, Key Observations, Trend vs Last Week. Import the user-written fields (Key Observations, Overall Status, Trend) into `weekly_summaries`; computed fields will be recalculated from daily data.
3. **Exercise Log** — header on row 3: Date, Exercise, Sets, Reps, Modification/Progression, Difficulty (1–10), Nerve Response During?, Notes. **Important quirk:** the Date cell is only filled on the first row of each session; subsequent exercise rows have a blank date and belong to the session above (forward-fill). Rows with no sets/reps ("-" or blank) mean the exercise wasn't performed that session — skip them. Time-based exercises (Forearm Plank, Hollowbody Hold) record seconds in the Reps column — map to `hold_seconds`.

Use `openpyxl` or `pandas`. Be tolerant of messy values ("-", blanks, "Yes - Many", trailing spaces, "0.5" pain levels). Import must be idempotent (re-running doesn't duplicate; match on date / date+exercise).

---

## 7. Phase 2 (DO NOT BUILD YET — design for it)

Future feature: an in-app chat to discuss recovery data with Claude (Anthropic API), replacing the current manual workflow of pasting the spreadsheet into Claude. Planned capabilities:

- "Generate my weekly summary" — drafts the Key Observations narrative from the week's daily entries, pain events, exercise logs, and sit/stand data (the existing weekly summaries in the spreadsheet are good examples of the desired output style).
- Free-form Q&A over the data ("is my sitting time correlated with flare-ups?", "compare this week to week 5").

Architectural accommodations to make **now**:

- Keep all data queryable through clean service-layer functions (e.g. `get_week_bundle(week_start)` returning entries + events + sessions + timer aggregates as one serialisable object) so it can later be serialised into an LLM context.
- Reserve `backend/app/routers/ai.py` and an `ANTHROPIC_API_KEY` env var in `.env.example` (unused in Phase 1).
- Add a placeholder "AI Insights — coming soon" nav item only if trivial; otherwise omit entirely.

---

## 8. Quality Bar

- Type hints throughout the backend; Pydantic models for every request/response.
- Backend tests (pytest) for: timer start/switch/stop logic, weekly aggregation maths, xlsx import parsing (including the forward-filled dates and "-" handling), and entry upsert.
- A handful of frontend component tests is enough; prioritise the timer store logic.
- `README.md` at the root: how to run dev and prod compose, how to import the spreadsheet, API overview.
- Lint/format: ruff for Python, prettier + eslint for the frontend.
- All timestamps UTC in the DB; dates computed in the configured local timezone (this matters — a sitting interval at 11pm must land on the correct local day).

## 9. Build Order

1. Repo scaffold, compose files, hello-world FastAPI + SvelteKit talking to each other in containers.
2. DuckDB layer + migrations + schema above.
3. Daily entries API + Today page.
4. Timer API + Timer page (server-side running interval).
5. Exercise catalogue, sessions API + Exercises page with previous-session prefill.
6. History page + stats endpoint + charts.
7. Weekly aggregation + Weekly page.
8. XLSX import endpoint + a simple upload UI in settings.
9. Tests, README, polish.
