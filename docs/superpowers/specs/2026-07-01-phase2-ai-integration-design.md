# NerveTrack Phase 2 — AI over your recovery data

**Status:** Design approved, pending implementation plan
**Date:** 2026-07-01

## 1. Goal

Bring the LLM inside NerveTrack so it can:

1. **Chat anytime** about the user's recovery, answering tailored questions
   grounded in the user's own tracking data (e.g. "is my sitting time correlated
   with flare-ups?", "compare this week to week 5").
2. **Perform the weekly review** — draft the retrospective narrative and a
   forward-looking plan for a given week.

It must support the **main providers via user-supplied keys** — Anthropic,
OpenAI, Google Gemini, OpenRouter, and local **Ollama** — with maximum
flexibility over which model is used. Because the app tracks **health data**,
privacy is a first-class concern: the local Ollama path must let a user run
everything on-box with no data egress.

This replaces the old Phase-1 accommodation (a single reserved, unused
`ANTHROPIC_API_KEY`) with a real, multi-provider, per-user integration.

## 2. Architecture overview

A **server-orchestrated, tool-calling chat**. The backend runs the LiteLLM
tool-calling loop, executes read-only tools against the existing service layer
(scoped to the session user), and streams the answer to the frontend over
**SSE**. Three user-facing surfaces:

- **Chat page** (`/chat`) — persisted conversation threads with a sidebar.
- **Weekly page button** — "✨ Draft with AI" fills the editable Key
  Observations and Next Steps fields.
- **Settings** — per-user provider / model / API-key configuration.

**Core security principle:** the model never receives or chooses a `user_id`.
Every tool executes with the `user_id` from the authenticated session, so the
LLM structurally cannot read another account's data.

## 3. Provider layer (LiteLLM)

A thin `LLMService` wraps the `litellm` library, which natively speaks all five
target providers and normalizes tool-calling + streaming across them.

- Config resolves **per-user** from the DB:
  `{ model: str, api_key: str (decrypted in-memory), base_url: str | None }`.
- The `model` field is LiteLLM's `provider/model` string
  (`ollama/llama3.1`, `openrouter/anthropic/claude-...`,
  `gemini/gemini-2.5-pro`, `anthropic/claude-...`, `openai/gpt-...`), so **new
  models require zero code changes** — the user just types a string.
- `base_url` covers Ollama, OpenRouter, and any OpenAI-compatible endpoint.
- If a user has no config, the chat / weekly UI prompts them to set one in
  Settings (the backend returns a clear "not configured" error, not a 500).

## 4. Data-access tools

All tools are **read-only** and wrapped with a `user_id`-injecting dispatcher.
Each maps onto an existing service function; together they cover **all** of the
user's data (daily entries, note log, pain events, strengthening sessions,
sit/stand timer timeline + totals, weekly aggregates, and history stats).

| Tool | Backs onto | Covers |
|---|---|---|
| `list_weeks()` | `weekly.list_weeks` | week index for navigation |
| `get_week_summary(week_start)` | `weekly.get_week_bundle` | entries + events + sessions + timer aggregates for a week |
| `get_daily_entry(date)` | `entries.get_entry` | full day incl. pain events + note log |
| `get_daily_entries(from, to)` | `entries` (range) | daily summary rows over a range |
| `get_pain_events(from, to)` | `entries` | flare events with context |
| `get_timer_day(date)` | `timer.day` | the sit/stand interval timeline (timer page) |
| `get_posture_totals(from, to)` | `timer.posture_totals` | sitting / standing minutes |
| `get_strengthening_sessions(from, to)` | `sessions` | exercise logs |
| `get_stats(from, to)` | `stats` | history / chart aggregates |

**The loop:** model → tool calls → dispatcher runs each tool scoped to the
session `user_id` → results returned to the model → repeat until the model emits
a final answer, which streams to the client. A **max-iterations guard** (e.g.
8 rounds) prevents runaway tool loops.

Some existing services are keyed to a single day (`get_entry`, `timer.day`).
Range tools (`get_daily_entries`, `get_pain_events`, `get_posture_totals`,
`get_strengthening_sessions`) are implemented as thin service additions that
iterate/aggregate over a date range where a range function does not already
exist. These live in the service layer, not the tool dispatcher.

## 5. Chat model & persistence

Conversations are persisted per-user as threads (chat-app style sidebar).

- **New chat** creates a `conversations` row; the first user message seeds a
  title (a short generated or truncated label).
- Each turn (user / assistant / tool) is stored in `messages` so a thread
  replays exactly, including tool activity.
- Threads can be reopened, continued, and deleted.

**Streaming:** the chat endpoint streams the assistant's answer token-by-token
over SSE. Tool-call activity may be surfaced as lightweight status events
("looking at week 5…") but the assistant text is the primary stream. The full
assistant message (and any tool calls) is persisted once the stream completes.

## 6. Weekly review

The Weekly page gains a "✨ Draft with AI" button. It POSTs to a weekly-draft
endpoint that runs the same tool loop with a fixed prompt, seeded with that
week's `get_week_bundle`, and produces **two** outputs:

- **Key Observations** — the retrospective narrative (what happened),
  in the established style of the user's historical summaries.
- **Next Steps** — forward-looking suggestions / plan for the upcoming week.

Both land in **separate editable fields**. Nothing is auto-saved — the user
reviews both and hits Save. Key Observations = retrospective; Next Steps =
forward plan.

## 7. Data model (new migrations)

New migration files (`0004_*`, `0005_*`) added to
`backend/app/migrations/`, applied in order by the built-in runner.

**`llm_settings`** — one row per user:

```
llm_settings(
  user_id     PK / FK -> users,
  provider    TEXT,        -- display label (e.g. "anthropic", "ollama")
  model       TEXT,        -- litellm model string
  api_key_enc TEXT,        -- Fernet-encrypted; NULL/empty allowed (e.g. Ollama)
  base_url    TEXT,        -- optional; Ollama / OpenRouter / compat endpoints
  updated_at  TIMESTAMP
)
```

**`conversations`**:

```
conversations(
  id         PK,
  user_id    FK -> users,
  title      TEXT,
  created_at TIMESTAMP,
  updated_at TIMESTAMP
)
```

**`messages`**:

```
messages(
  id              PK,
  conversation_id FK -> conversations (ON DELETE CASCADE),
  role            TEXT,   -- 'user' | 'assistant' | 'tool'
  content         TEXT,
  tool_calls_json TEXT,   -- serialized tool calls/results for replay, nullable
  created_at      TIMESTAMP
)
```

**`weekly_summaries` alteration** — add a user-editable column:

```
ALTER TABLE weekly_summaries ADD COLUMN next_steps TEXT;
```

`WeeklyUserFields` / `WeeklySummary` gain a `next_steps` field so it flows
through `get_week` / `save_week` alongside `key_observations`.

## 8. Security

- **Encryption key** from a new `NERVETRACK_SECRET_KEY` env var (Fernet). The
  backend refuses to store API keys and returns a clear error if it is unset.
- API keys are **never** returned to the frontend — the Settings UI shows only a
  "configured ✓ / not set" indicator and a replace field.
- Keys are decrypted only in-memory at call time and redacted from logs.
- The local **Ollama** path (no key, custom `base_url`) means health data can
  stay entirely on-box with no external egress.
- Tools are read-only and `user_id`-scoped; the model cannot mutate data or
  reach another user's records.

## 9. Backend / frontend deltas

**Backend**
- Deps: `litellm`, `cryptography`.
- Replace `routers/ai.py` stub with real routers: chat (create/list/get/delete
  conversations + streaming send), weekly-draft, and llm-settings CRUD.
- New services: `llm.py` (LiteLLM wrapper + config resolution + encryption),
  `tools.py` (tool schemas + `user_id`-injecting dispatcher), plus small range
  helpers in existing services.
- New Pydantic models for conversations, messages, llm settings, and the
  weekly-draft response.

**Frontend**
- New `/chat` route: thread sidebar + streaming message view.
- Settings: an LLM configuration section (provider, model string, API key,
  optional base URL), showing configured/not-set state.
- Weekly page: "✨ Draft with AI" button + a separate **Next Steps** textarea
  under Key Observations; the draft action populates both.
- New nav item for Chat.

## 10. Testing

**Backend (pytest, no live API calls — LiteLLM mocked):**
- Tool dispatcher injects the session `user_id` and rejects/ignores any
  model-supplied `user_id`.
- Config resolution + encrypt/decrypt round-trip; clear error when
  `NERVETRACK_SECRET_KEY` is unset.
- The tool loop terminates (max-iterations guard) and produces a final answer
  with a mocked LiteLLM.
- Weekly-draft endpoint returns both Key Observations and Next Steps.
- `next_steps` round-trips through `get_week` / `save_week`.

**Frontend:**
- A couple of component tests for the chat store / streaming reducer.

## 11. Out of scope (YAGNI)

- Automatic/scheduled weekly reviews (no background scheduler exists; the button
  is the trigger).
- RAG / embeddings (structured tool-calling covers the data).
- Sharing conversations between users or exporting them.
- Model-initiated writes to tracking data (all tools are read-only).
