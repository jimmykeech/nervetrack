# Weekly Review Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the weekly page's AI review come back as sectioned markdown that cites earlier program weeks, and present it as a readable document with inline editing and auto-save.

**Architecture:** Four backend-first changes then three frontend ones. The draft bundle gains program history so the model has something to compare against; the prompt asks for `###`-sectioned markdown; the response is parsed with delimiters instead of an unguarded `json.loads`; then `weekly/+page.svelte` is rebuilt from a form into a document. No database migration — `key_observations` and `next_steps` keep their meaning and simply hold richer markdown.

**Tech Stack:** Python 3.12 / FastAPI / SQLite (backend, pytest + ruff), SvelteKit 2 + Svelte 5 runes / TypeScript (frontend, vitest + eslint + prettier), litellm for provider-agnostic LLM calls, marked + DOMPurify for markdown rendering.

**Spec:** `docs/superpowers/specs/2026-08-12-weekly-review-redesign-design.md`

## Global Constraints

- Backend line length is 100 (`ruff`, `backend/pyproject.toml:37`). Lint with `backend/.venv/bin/python -m ruff check .` from `backend/`.
- Backend tests run from `backend/` as `.venv/bin/python -m pytest`. `asyncio_mode = "auto"`, so `async def test_*` needs no decorator.
- Frontend checks run from `frontend/`: `npm test` (vitest), `npm run check` (svelte-check), `npm run lint` (prettier + eslint). Run `npm run format` before committing frontend changes.
- Every `api.saveWeek` call must send all four user fields. `save_week` (`backend/app/services/weekly.py:108`) is a full overwrite — an omitted field is written as `NULL`.
- LLM output is untrusted. All markdown must render through `renderMarkdown` from `$lib/markdown`, never `{@html}` on a raw string.
- Never invent numbers in prompts or fixtures; the model may only cite weeks present in `history`.
- Do not add a database migration, a new stored field, a markdown toolbar, or a Settings control for review depth. All are explicitly out of scope.

## File Structure

| File | Responsibility | Tasks |
|---|---|---|
| `backend/app/services/weekly.py` | Add `program_week`, `history`, `recent_reviews` to `get_week_bundle` | 1 |
| `backend/tests/test_weekly.py` | Bundle history coverage | 1 |
| `backend/app/services/llm.py` | Delimiter constants + `_parse_draft`; rewritten `draft_weekly` prompt | 2, 3 |
| `backend/tests/test_llm.py` | Parser and prompt coverage | 2, 3 |
| `frontend/src/routes/weekly/+page.svelte` | Auto-save, document presentation, inline controls | 4, 5, 6 |

---

### Task 1: Program history in the draft bundle

**Files:**
- Modify: `backend/app/services/weekly.py:169-190` (`get_week_bundle`)
- Test: `backend/tests/test_weekly.py`

**Interfaces:**
- Consumes: `list_weeks(db, user_id) -> list[WeeklySummary]` (already exists, `weekly.py:146`, returns **descending** by `week_start`); `WeeklyUserFields` from `app.models.weekly`.
- Produces: `get_week_bundle(db, user_id, week_start) -> dict` with new keys `program_week: int`, `history: list[dict]`, `recent_reviews: list[dict]`. Task 3 relies on these key names appearing in the JSON handed to the model.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_weekly.py`. Add `from app.models.weekly import WeeklyUserFields` to the imports at the top of the file.

```python
def _seed_day(db, user_id, iso, status="G", worst=2):
    entries_service.upsert_entry(
        db,
        user_id,
        date.fromisoformat(iso),
        DailyEntryUpsert(
            status=status,
            sharp_pain_episodes=1,
            tingling_level=2,
            strengthening_done=False,
            worst_pain=worst,
        ),
    )


# The default week start day is 4 (Friday); 2026-06-12 is a Friday, so each
# date below opens a new tracking week.
WEEK_STARTS = ["2026-06-12", "2026-06-19", "2026-06-26", "2026-07-03", "2026-07-10"]


def test_bundle_history_covers_prior_weeks_only(db, user_id):
    for iso in WEEK_STARTS[:3]:
        _seed_day(db, user_id, iso)

    bundle = service.get_week_bundle(db, user_id, date(2026, 6, 26))

    assert bundle["program_week"] == 3
    assert [h["program_week"] for h in bundle["history"]] == [1, 2]
    assert [h["week_start"] for h in bundle["history"]] == ["2026-06-12", "2026-06-19"]
    # Metrics only — never day-level data.
    assert "days" not in bundle["history"][0]
    assert bundle["history"][0]["avg_tingling_level"] is not None


def test_bundle_history_empty_for_first_week(db, user_id):
    _seed_day(db, user_id, "2026-06-12")

    bundle = service.get_week_bundle(db, user_id, date(2026, 6, 12))

    assert bundle["program_week"] == 1
    assert bundle["history"] == []
    assert bundle["recent_reviews"] == []


def test_bundle_recent_reviews_caps_at_three_most_recent(db, user_id):
    for iso in WEEK_STARTS:
        _seed_day(db, user_id, iso)
    for iso in WEEK_STARTS[:4]:
        service.save_week(
            db,
            user_id,
            date.fromisoformat(iso),
            WeeklyUserFields(key_observations=f"obs {iso}"),
        )

    bundle = service.get_week_bundle(db, user_id, date(2026, 7, 10))

    assert [r["program_week"] for r in bundle["recent_reviews"]] == [4, 3, 2]
    assert bundle["recent_reviews"][0]["key_observations"] == "obs 2026-07-03"


def test_bundle_recent_reviews_skips_weeks_without_observations(db, user_id):
    for iso in WEEK_STARTS[:3]:
        _seed_day(db, user_id, iso)
    service.save_week(
        db,
        user_id,
        date.fromisoformat(WEEK_STARTS[0]),
        WeeklyUserFields(key_observations="only this one"),
    )

    bundle = service.get_week_bundle(db, user_id, date(2026, 6, 26))

    assert [r["program_week"] for r in bundle["recent_reviews"]] == [1]


def test_bundle_history_is_user_scoped(db, user_id, make_user):
    other = make_user("other@example.com", "sub-other", "Other")
    for iso in WEEK_STARTS[:3]:
        _seed_day(db, other, iso)
    _seed_day(db, user_id, WEEK_STARTS[2])

    bundle = service.get_week_bundle(db, user_id, date(2026, 6, 26))

    # This user has logged only one week, so it is their week 1 with no history.
    assert bundle["program_week"] == 1
    assert bundle["history"] == []
```

- [ ] **Step 2: Run the tests to verify they fail**

Run from `backend/`:

```bash
.venv/bin/python -m pytest tests/test_weekly.py -k bundle -v
```

Expected: FAIL — `KeyError: 'program_week'`.

- [ ] **Step 3: Implement the bundle changes**

Replace the body of `get_week_bundle` in `backend/app/services/weekly.py:169-190` with:

```python
def get_week_bundle(db: Database, user_id: UUID, week_start: date) -> dict[str, Any]:
    """Serialisable bundle of a user's week of data, plus program history.

    ``history`` carries every prior week's computed metrics (no day-level data)
    so the AI drafter can compare this week against earlier ones by program
    week number. ``recent_reviews`` carries the last three saved reviews for
    narrative continuity.
    """
    from app.services import entries as entries_service

    week_end = week_start + timedelta(days=6)
    days = []
    cursor = week_start
    while cursor <= week_end:
        entry = entries_service.get_entry(db, user_id, cursor)
        if entry is not None:
            days.append(entry.model_dump(mode="json"))
        cursor += timedelta(days=1)

    # list_weeks returns newest-first; number the weeks oldest-first so week 1
    # is the first week containing any logged entry.
    tracked = sorted(list_weeks(db, user_id), key=lambda w: w.week_start)
    numbers = {w.week_start: i for i, w in enumerate(tracked, start=1)}
    prior = [w for w in tracked if w.week_start < week_start]

    history = [
        {
            "program_week": numbers[w.week_start],
            "week_start": w.week_start.isoformat(),
            "overall_status": w.overall_status,
            "trend_vs_last_week": w.trend_vs_last_week,
            **w.computed.model_dump(mode="json"),
        }
        for w in prior
    ]
    reviewed = [w for w in prior if w.key_observations][-3:]
    recent_reviews = [
        {
            "program_week": numbers[w.week_start],
            "week_start": w.week_start.isoformat(),
            "key_observations": w.key_observations,
            "next_steps": w.next_steps,
        }
        for w in reversed(reviewed)
    ]

    return {
        "week_start": week_start.isoformat(),
        "week_end": week_end.isoformat(),
        "program_week": numbers.get(week_start, len(tracked) + 1),
        "summary": get_week(db, user_id, week_start).model_dump(mode="json"),
        "days": days,
        "history": history,
        "recent_reviews": recent_reviews,
    }
```

Notes for the implementer:
- `reversed(reviewed)` yields most-recent-first. `reversed()` returns an iterator, so it must be consumed by the comprehension — do not try to slice it.
- `numbers.get(week_start, len(tracked) + 1)` covers a week that sits beyond the logged range, so a freshly-started week still numbers sensibly instead of raising `KeyError`.
- No cap on `history`. At ~15 numbers per week a full year is roughly 3–4k tokens. Do not add slicing.

- [ ] **Step 4: Run the tests to verify they pass**

```bash
.venv/bin/python -m pytest tests/test_weekly.py -v
```

Expected: PASS, including the pre-existing weekly tests.

- [ ] **Step 5: Lint**

```bash
.venv/bin/python -m ruff check app tests
```

Expected: `All checks passed!`

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/weekly.py backend/tests/test_weekly.py
git commit -m "feat(weekly): add program history to the AI draft bundle"
```

---

### Task 2: Delimiter parsing for the draft response

**Files:**
- Modify: `backend/app/services/llm.py:104-124` (`draft_weekly`)
- Test: `backend/tests/test_llm.py:97-107` (replaces `test_draft_weekly_parses_json`)

**Interfaces:**
- Consumes: `WeeklyDraftResponse` from `app.models.ai` (fields `key_observations: str`, `next_steps: str`).
- Produces: module-level `KEY_MARKER = "<<<KEY_OBSERVATIONS>>>"`, `NEXT_MARKER = "<<<NEXT_STEPS>>>"`, and `_parse_draft(raw: str) -> WeeklyDraftResponse`. Task 3 references `KEY_MARKER` and `NEXT_MARKER` when building the prompt.

**Why:** the current parser is `json.loads(raw[raw.find("{"): raw.rfind("}") + 1])` with no error handling (`llm.py:120`), so one unescaped newline is a 500. Task 3 starts demanding hundreds of words of multi-line markdown, which is exactly where models mis-escape JSON string values.

- [ ] **Step 1: Write the failing tests**

In `backend/tests/test_llm.py`, delete `test_draft_weekly_parses_json` (lines 97–107) and add:

```python
def test_parse_draft_splits_on_markers():
    raw = (
        "<<<KEY_OBSERVATIONS>>>\n"
        "### The week at a glance\n"
        "All seven days green.\n\n"
        "### Analysis\n"
        "**The painting weekend absorbed without a flare.**\n"
        "<<<NEXT_STEPS>>>\n"
        "Hold the volume.\n\n"
        "1. Keep the 3-set goblet squat\n"
    )

    out = llm._parse_draft(raw)

    assert out.key_observations.startswith("### The week at a glance")
    assert "### Analysis" in out.key_observations
    assert "**The painting weekend absorbed without a flare.**" in out.key_observations
    assert out.next_steps.startswith("Hold the volume.")
    assert "1. Keep the 3-set goblet squat" in out.next_steps
    # The markers themselves never leak into the stored fields.
    assert llm.KEY_MARKER not in out.key_observations
    assert llm.NEXT_MARKER not in out.key_observations


def test_parse_draft_without_next_marker_keeps_everything_as_observations():
    out = llm._parse_draft("<<<KEY_OBSERVATIONS>>>\n### Analysis\nSteady week.")

    assert out.key_observations == "### Analysis\nSteady week."
    assert out.next_steps == ""


def test_parse_draft_without_markers_never_raises():
    out = llm._parse_draft("Sorry, I could not read the data.")

    assert out.key_observations == "Sorry, I could not read the data."
    assert out.next_steps == ""


def test_parse_draft_ignores_preamble_before_the_first_marker():
    out = llm._parse_draft("Here you go:\n<<<KEY_OBSERVATIONS>>>\nSteady.\n<<<NEXT_STEPS>>>\nWalk.")

    assert out.key_observations == "Steady."
    assert out.next_steps == "Walk."


def test_parse_draft_splits_on_next_marker_even_without_the_key_marker():
    out = llm._parse_draft("Steady week.\n<<<NEXT_STEPS>>>\nWalk more.")

    assert out.key_observations == "Steady week."
    assert out.next_steps == "Walk more."


def test_parse_draft_strips_markers_the_model_echoed_back():
    raw = (
        "<<<KEY_OBSERVATIONS>>>\n"
        "Steady.\n"
        "<<<KEY_OBSERVATIONS>>>\n"
        "Still steady.\n"
        "<<<NEXT_STEPS>>>\n"
        "Walk.\n"
        "<<<NEXT_STEPS>>>\n"
        "And stretch.\n"
    )

    out = llm._parse_draft(raw)

    for field in (out.key_observations, out.next_steps):
        assert llm.KEY_MARKER not in field
        assert llm.NEXT_MARKER not in field
    assert "Still steady." in out.key_observations
    assert "And stretch." in out.next_steps


async def test_draft_weekly_returns_parsed_fields(monkeypatch, cfg):
    async def fake_acompletion(**kwargs):
        msg = types.SimpleNamespace(
            content="<<<KEY_OBSERVATIONS>>>\nsteady\n<<<NEXT_STEPS>>>\nwalk more"
        )
        return types.SimpleNamespace(choices=[types.SimpleNamespace(message=msg)])

    monkeypatch.setattr(llm.litellm, "acompletion", fake_acompletion)
    out = await llm.draft_weekly(cfg, {"week_start": "2026-06-22", "days": []})
    assert out.key_observations == "steady" and out.next_steps == "walk more"
```

If `json` is no longer referenced anywhere in `test_llm.py` after deleting the old test, remove its import — ruff's `F401` will flag it otherwise.

- [ ] **Step 2: Run the tests to verify they fail**

```bash
.venv/bin/python -m pytest tests/test_llm.py -k draft -v
```

Expected: FAIL — `AttributeError: module 'app.services.llm' has no attribute '_parse_draft'`.

- [ ] **Step 3: Implement the parser**

In `backend/app/services/llm.py`, add the markers just below `SYSTEM_PROMPT` (after line 25):

```python
KEY_MARKER = "<<<KEY_OBSERVATIONS>>>"
NEXT_MARKER = "<<<NEXT_STEPS>>>"
```

Add the parser above `draft_weekly`:

```python
def _strip_markers(text: str) -> str:
    """Drop any stray marker the model echoed back, so none reaches the user."""
    return text.replace(KEY_MARKER, "").replace(NEXT_MARKER, "").strip()


def _parse_draft(raw: str) -> WeeklyDraftResponse:
    """Split a delimited draft into its two fields.

    Never raises: a malformed reply still yields something the user can edit
    rather than a 500. Delimiters are used instead of JSON because the payload
    is multi-line markdown, which models routinely fail to escape inside a JSON
    string value.

    Markers are located by position rather than by membership, so a reply that
    carries only the NEXT marker still splits correctly instead of dumping the
    marker text into key_observations. Repeated markers are stripped: the
    prompt instructs the model to emit these exact strings, so a model echoing
    its own instructions is a realistic reply, and the result is rendered
    straight to the user.
    """
    key_at = raw.find(KEY_MARKER)
    body = raw[key_at + len(KEY_MARKER) :] if key_at != -1 else raw
    next_at = body.find(NEXT_MARKER)
    if next_at == -1:
        obs, nxt = body, ""
    else:
        obs = body[:next_at]
        nxt = body[next_at + len(NEXT_MARKER) :]
    return WeeklyDraftResponse(
        key_observations=_strip_markers(obs), next_steps=_strip_markers(nxt)
    )
```

Then replace the tail of `draft_weekly` (`llm.py:119-124`) — leave the prompt alone, Task 3 handles it:

```python
    return _parse_draft(resp.choices[0].message.content or "")
```

If `json` is now unused in `llm.py`, keep the import — `stream_chat` still uses `json.loads` and `json.dumps` (lines 89, 96).

- [ ] **Step 4: Run the tests to verify they pass**

```bash
.venv/bin/python -m pytest tests/test_llm.py -v
```

Expected: PASS.

- [ ] **Step 5: Lint**

```bash
.venv/bin/python -m ruff check app tests
```

Expected: `All checks passed!`

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/llm.py backend/tests/test_llm.py
git commit -m "fix(ai): parse weekly drafts with delimiters instead of bare json.loads"
```

---

### Task 3: Ask the drafter for sectioned markdown

**Files:**
- Modify: `backend/app/services/llm.py` (`draft_weekly` prompt, formerly lines 107-113)
- Test: `backend/tests/test_llm.py`

**Interfaces:**
- Consumes: `KEY_MARKER`, `NEXT_MARKER`, `_parse_draft` from Task 2; the `history` / `program_week` / `recent_reviews` bundle keys from Task 1.
- Produces: no new symbols. `draft_weekly`'s signature is unchanged.

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_llm.py`:

```python
async def test_draft_weekly_prompt_requests_sections_and_includes_history(monkeypatch, cfg):
    captured: dict = {}

    async def fake_acompletion(**kwargs):
        captured.update(kwargs)
        msg = types.SimpleNamespace(content="<<<KEY_OBSERVATIONS>>>\nx\n<<<NEXT_STEPS>>>\ny")
        return types.SimpleNamespace(choices=[types.SimpleNamespace(message=msg)])

    monkeypatch.setattr(llm.litellm, "acompletion", fake_acompletion)
    bundle = {
        "week_start": "2026-08-04",
        "program_week": 21,
        "days": [],
        "history": [{"program_week": 8, "avg_tingling_level": "1.1"}],
        "recent_reviews": [],
    }

    await llm.draft_weekly(cfg, bundle)

    prompt = captured["messages"][1]["content"]
    # The section menu the model is told to choose from.
    assert "### The week at a glance" in prompt
    assert "### What stood out" in prompt
    assert "### Analysis" in prompt
    assert "### Watch-outs" in prompt
    # The response contract matches what _parse_draft reads.
    assert llm.KEY_MARKER in prompt
    assert llm.NEXT_MARKER in prompt
    # History is serialised into the prompt so past weeks can be cited.
    assert '"program_week": 8' in prompt
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
.venv/bin/python -m pytest tests/test_llm.py -k prompt_requests_sections -v
```

Expected: FAIL — `assert '### The week at a glance' in prompt`.

- [ ] **Step 3: Rewrite the prompt**

Replace the `prompt = (...)` assignment in `draft_weekly` with:

```python
    prompt = (
        "Draft this week's review from the JSON data below.\n\n"
        "Write both fields as markdown. Structure the key observations with `###` "
        "headings drawn from this menu, using ONLY the sections this week's data "
        "supports — skip any you would have to pad:\n\n"
        "  ### The week at a glance   — the headline numbers and how they compare\n"
        "  ### What stood out         — the notable events, sessions, and symptoms\n"
        "  ### Analysis               — why it matters\n"
        "  ### Watch-outs             — anything to keep an eye on\n\n"
        "Open Analysis with a single bolded sentence naming the most significant "
        "thing in this week's data, then argue it from the sequence of days: name "
        "the days, the numbers, and the exercises involved. Where `history` "
        'supports it, compare against earlier program weeks by number (e.g. "matching '
        'W8, W11, W17"). Never cite a week that is not present in `history`, and '
        "never invent a number.\n\n"
        "Aim for 350-500 words of key observations and 100-150 words of next steps. "
        "Write next steps as a short lead sentence followed by a numbered list.\n\n"
        "Respond in exactly this format, with no prose outside it:\n\n"
        f"{KEY_MARKER}\n(markdown)\n{NEXT_MARKER}\n(markdown)\n\n"
        "DATA:\n" + json.dumps(bundle, default=str)
    )
```

`SYSTEM_PROMPT` and the `extra_context` injection stay exactly as they are.

- [ ] **Step 4: Run the tests to verify they pass**

```bash
.venv/bin/python -m pytest tests/test_llm.py -v
```

Expected: PASS.

- [ ] **Step 5: Run the full backend suite and lint**

```bash
.venv/bin/python -m pytest && .venv/bin/python -m ruff check app tests
```

Expected: all tests pass, `All checks passed!`

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/llm.py backend/tests/test_llm.py
git commit -m "feat(ai): prompt the weekly drafter for sectioned markdown with history"
```

---

### Task 4: Auto-save on the weekly page

**Files:**
- Modify: `frontend/src/routes/weekly/+page.svelte`

**Interfaces:**
- Consumes: `api.saveWeek(weekStart, {overall_status?, key_observations?, trend_vs_last_week?, next_steps?})` (`frontend/src/lib/api.ts:178`).
- Produces: `saveState: 'idle' | 'saving' | 'saved'`, `save()`, and the `.weekhead` wrapper. Tasks 5 and 6 call `save()` and render inside `.weekhead`.

This task leaves the page fully working: the controls still look like they do today, but the Save button is gone and edits persist on their own.

**Note — a deliberate behaviour change:** `select()` currently seeds `editStatus` from `w.computed.suggested_status` when no status is saved (`+page.svelte:29`). With auto-save that would silently persist a suggestion the user never chose, so `editStatus` now starts `null` and the suggestion becomes a visible hint in Task 5.

- [ ] **Step 1: Add the save state**

**No debounce.** The Today page debounces because it has free-typing inputs; every control on this page is a discrete one-shot event, so a timer would coalesce nothing while opening a window in which switching weeks lands the in-flight save on the wrong week. `save()` runs immediately and guards its own `await` window instead.

In the `<script>` block, add after `let editingNext = $state(false);` (line 16):

```ts
  let saveState = $state<'idle' | 'saving' | 'saved'>('idle');
```

Replace `select()` (lines 27–36) with:

```ts
  function select(w: WeeklySummary) {
    selected = w;
    // Not `?? w.computed.suggested_status` — with auto-save that would persist a
    // status the user never picked. The suggestion is shown as a hint instead.
    editStatus = w.overall_status ?? null;
    editObs = w.key_observations ?? '';
    editTrend = w.trend_vs_last_week ?? '';
    editNext = w.next_steps ?? '';
    editingObs = false;
    editingNext = false;
    saveState = 'idle';
    message = '';
  }
```

Replace `save()` (lines 38–49) with:

```ts
  async function save() {
    if (!selected) return;
    const target = selected.week_start;
    saveState = 'saving';
    // All four fields go every time: save_week is a full overwrite, so an
    // omitted field is persisted as NULL.
    const updated = await api.saveWeek(target, {
      overall_status: editStatus ?? undefined,
      key_observations: editObs || undefined,
      trend_vs_last_week: editTrend || undefined,
      next_steps: editNext || undefined
    });
    weeks = weeks.map((w) => (w.week_start === updated.week_start ? updated : w));
    // The user may have switched weeks while the request was in flight; writing
    // back then would clobber the newly selected week with this one's data.
    if (selected?.week_start !== target) return;
    selected = updated;
    saveState = 'saved';
  }
```

- [ ] **Step 2: Wire the existing controls to it**

In `draftWithAi()` (lines 51–69), replace `message = 'Draft ready — review and Save.';` with `void save();`.

Replace the header line (line 96):

```svelte
    <h3 style="margin-top: 0">{selected.week_start} → {selected.week_end}</h3>
```

with:

```svelte
    <div class="weekhead">
      <h3>{selected.week_start} → {selected.week_end}</h3>
      <span class="save-ind">
        {#if saveState === 'saving'}<span class="saving">Saving…</span>
        {:else if saveState === 'saved'}<span class="saved">Saved ✓</span>{/if}
      </span>
    </div>
```

In the status buttons (lines 135–140), add the save call:

```svelte
        {#each ['G', 'A', 'R'] as s}
          <button
            class="opt {editStatus === s ? `status-${s}` : ''}"
            onclick={() => {
              editStatus = s as Status;
              void save();
            }}>{s}</button
          >
        {/each}
```

On the trend select (line 145), add a change handler:

```svelte
      <select bind:value={editTrend} onchange={() => void save()}>
```

On the two `Done` buttons (lines 161 and 177), save on collapse:

```svelte
          <button class="link" onclick={() => { editingObs = false; void save(); }}>Done</button>
```

```svelte
          <button class="link" onclick={() => { editingNext = false; void save(); }}>Done</button>
```

Delete the Save button and its message span (lines 188–189):

```svelte
    <button class="status-G" onclick={save}>Save</button>
    {#if message}<span class="saved" style="margin-left: 0.75rem">{message}</span>{/if}
```

and put the draft error message back where the draft button lives — replace the draft `<div class="field">` block (lines 150–154) with:

```svelte
    <div class="field">
      <button class="draft" onclick={draftWithAi} disabled={drafting}>
        {drafting ? 'Drafting…' : '✨ Draft with AI'}
      </button>
      {#if message}<span class="muted small" style="margin-left: 0.75rem">{message}</span>{/if}
    </div>
```

- [ ] **Step 3: Add the header styles**

Add to the `<style>` block:

```css
  .weekhead {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    flex-wrap: wrap;
    margin-bottom: 0.75rem;
  }
  .weekhead h3 {
    margin: 0;
  }
  .save-ind {
    margin-left: auto;
  }
```

- [ ] **Step 4: Verify**

From `frontend/`:

```bash
npm run format && npm run check && npm run lint && npm test
```

Expected: svelte-check reports 0 errors; eslint and prettier pass; vitest passes.

Then run the app and confirm by hand: pick a week, click a status button → `Saving…` then `Saved ✓`; reload the page and the status persisted; change the trend → saves; there is no Save button anywhere.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/routes/weekly/+page.svelte
git commit -m "feat(weekly): auto-save the week instead of an explicit Save button"
```

---

### Task 5: Present the review as a document

**Files:**
- Modify: `frontend/src/routes/weekly/+page.svelte`

**Interfaces:**
- Consumes: `renderMarkdown` from `$lib/markdown` (already imported at line 5); `selected.computed` fields from `WeeklyComputed`.
- Produces: `.strip`, `.review`, `.block`, `.blockhead` markup and the `.markdown` heading styles. Task 6 edits inside `.blockhead`.

- [ ] **Step 1: Replace the metrics grid with a strip**

Replace the whole `<div class="metrics">…</div>` block plus the `G/A/R days` paragraph (lines 97–130) with:

```svelte
    <div class="strip tnum">
      <span><strong>{selected.computed.strengthening_sessions}</strong> sessions</span>
      <span><strong>{selected.computed.avg_pain_episodes_per_day ?? '—'}</strong> episodes/day</span>
      <span><strong>{selected.computed.avg_tingling_level ?? '—'}</strong> tingling</span>
      <span><strong>{selected.computed.worst_pain ?? '—'}</strong> worst pain</span>
      <span><strong>{selected.computed.days_logged}</strong> days</span>
      <span><strong>{Math.round(selected.computed.sitting_minutes / 60)}h</strong> sitting</span>
      <span
        ><strong
          >{selected.computed.green_days}/{selected.computed.amber_days}/{selected.computed
            .red_days}</strong
        > G/A/R</span
      >
    </div>
```

- [ ] **Step 2: Rebuild the two review fields as document blocks**

Replace both `<div class="field">` blocks for Key observations and Next steps (lines 155–187) with:

```svelte
    <div class="review">
      <section class="block">
        <div class="blockhead">
          <span class="label-caps">Key observations</span>
          {#if editObs && !editingObs}
            <button class="link" aria-label="Edit key observations" onclick={() => (editingObs = true)}
              >✎ Edit</button
            >
          {:else if editingObs}
            <button
              class="link"
              onclick={() => {
                editingObs = false;
                void save();
              }}>Done</button
            >
          {/if}
        </div>
        {#if editingObs}
          <textarea
            bind:value={editObs}
            rows="16"
            aria-label="Key observations markdown"
            placeholder="What stood out this week…"
          ></textarea>
        {:else if editObs}
          <!-- eslint-disable-next-line svelte/no-at-html-tags -- renderMarkdown sanitizes via DOMPurify -->
          <div class="markdown">{@html renderMarkdown(editObs)}</div>
        {:else}
          <p class="muted small empty">No review yet — ✨ Draft with AI, or ✎ to write one.</p>
        {/if}
      </section>

      <section class="block">
        <div class="blockhead">
          <span class="label-caps">Next steps</span>
          {#if editNext && !editingNext}
            <button class="link" aria-label="Edit next steps" onclick={() => (editingNext = true)}
              >✎ Edit</button
            >
          {:else if editingNext}
            <button
              class="link"
              onclick={() => {
                editingNext = false;
                void save();
              }}>Done</button
            >
          {/if}
        </div>
        {#if editingNext}
          <textarea
            bind:value={editNext}
            rows="8"
            aria-label="Next steps markdown"
            placeholder="Plan for the upcoming week…"
          ></textarea>
        {:else if editNext}
          <!-- eslint-disable-next-line svelte/no-at-html-tags -- renderMarkdown sanitizes via DOMPurify -->
          <div class="markdown">{@html renderMarkdown(editNext)}</div>
        {:else}
          <p class="muted small empty">Nothing planned yet — ✨ Draft with AI, or ✎ to write one.</p>
        {/if}
      </section>
    </div>
```

Note the empty state now shows when a field is blank, replacing the old "show the textarea directly" behaviour — the ✎ opens it instead.

- [ ] **Step 3: Replace the styles**

In the `<style>` block, delete the `.metrics`, `.metrics div`, `.metrics strong`, `.fieldhead` and `.rendered` rules, plus the `@media (max-width: 640px)` block that targets `.metrics`. Keep `.weeklist`, `.weekchip`, `.weekchip.sel`, `.link`, the `.weekhead` / `.save-ind` rules from Task 4, and — for now — `.opt`, which still styles the status buttons until Task 6 replaces them. Then add:

```css
  .strip {
    display: flex;
    flex-wrap: wrap;
    gap: 0.4rem 1.1rem;
    padding: 0.55rem 0.9rem;
    background: var(--surface-2);
    border-radius: var(--r-pill);
    margin-bottom: 1.1rem;
    font-size: 0.8rem;
    color: var(--text-muted);
  }
  .strip strong {
    color: var(--text);
    font-size: 0.95rem;
    margin-right: 0.2rem;
  }

  .review {
    max-width: 62ch;
  }
  .block + .block {
    border-top: 1px solid var(--border);
    margin-top: 1.25rem;
    padding-top: 1.25rem;
  }
  .blockhead {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 0.4rem;
  }
  .empty {
    margin: 0;
  }
  textarea {
    font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
    font-size: 0.85rem;
    line-height: 1.5;
  }

  .markdown {
    line-height: 1.7;
  }
  .markdown :global(> :first-child) {
    margin-top: 0;
  }
  .markdown :global(> :last-child) {
    margin-bottom: 0;
  }
  /* The AI writes `###`; h2/h4 are styled the same as a fallback in case the
     model picks a different level. */
  .markdown :global(h2),
  .markdown :global(h3),
  .markdown :global(h4) {
    font-family: var(--font-display);
    font-size: 0.72rem;
    font-weight: 700;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: var(--accent);
    margin: 1.4rem 0 0.4rem;
  }
  .markdown :global(p),
  .markdown :global(ul),
  .markdown :global(ol) {
    margin: 0 0 0.85rem;
  }
  .markdown :global(ul),
  .markdown :global(ol) {
    padding-left: 1.25rem;
  }
  .markdown :global(li) {
    margin: 0.25rem 0;
  }
  .markdown :global(strong) {
    color: var(--text);
  }
```

- [ ] **Step 4: Verify**

```bash
npm run format && npm run check && npm run lint && npm test
```

Expected: 0 errors from svelte-check; eslint and prettier pass; vitest passes.

By hand: paste markdown containing `### The week at a glance`, a paragraph, a `**bold**` sentence and a numbered list into Key observations, click Done, and confirm the heading renders as a small uppercase accent label, the prose sits at a comfortable measure, and a rule separates the two blocks. Confirm a week with an old plain-text review still renders as plain paragraphs. Confirm the metrics strip wraps rather than overflowing at 375px wide.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/routes/weekly/+page.svelte
git commit -m "feat(weekly): present the review as a document with section labels"
```

---

### Task 6: Inline status/trend pills and draft confirmation

**Files:**
- Modify: `frontend/src/routes/weekly/+page.svelte`

**Interfaces:**
- Consumes: `save()` from Task 4; `.weekhead` from Task 4; `statusClass` (line 19).
- Produces: nothing downstream — this is the last task.

- [ ] **Step 1: Add the expansion state and handler**

In the `<script>` block, add alongside the other `$state` declarations:

```ts
  let editingStatus = $state(false);
  let editingTrend = $state(false);
```

Add to `select()`, after `editingNext = false;`:

```ts
    editingStatus = false;
    editingTrend = false;
```

Add a handler beside `save()`:

```ts
  function pickStatus(s: Status) {
    editStatus = s;
    editingStatus = false;
    void save();
  }
```

- [ ] **Step 2: Move status and trend into the header**

Replace the `.weekhead` block from Task 4 with:

```svelte
    <div class="weekhead">
      <h3>{selected.week_start} → {selected.week_end}</h3>

      {#if editingStatus}
        <span class="statuspick">
          {#each ['G', 'A', 'R'] as s}
            <button class="pill {statusClass[s]}" onclick={() => pickStatus(s as Status)}>{s}</button
            >
          {/each}
        </span>
      {:else if editStatus}
        <button
          class="pill {statusClass[editStatus]}"
          aria-expanded="false"
          aria-label="Change overall status"
          onclick={() => (editingStatus = true)}>{editStatus}</button
        >
      {:else}
        <button
          class="pill unset"
          aria-expanded="false"
          onclick={() => (editingStatus = true)}>Set status</button
        >
        <span class="muted small">suggested {selected.computed.suggested_status}</span>
      {/if}

      {#if editingTrend}
        <select
          bind:value={editTrend}
          onchange={() => {
            editingTrend = false;
            void save();
          }}
        >
          <option value="">—</option>
          {#each trends as t}<option value={t}>{t}</option>{/each}
        </select>
      {:else}
        <button
          class="pill"
          aria-label="Change trend vs last week"
          onclick={() => (editingTrend = true)}>{editTrend || 'Set trend'}</button
        >
      {/if}

      <span class="save-ind">
        {#if saveState === 'saving'}<span class="saving">Saving…</span>
        {:else if saveState === 'saved'}<span class="saved">Saved ✓</span>{/if}
      </span>
    </div>
```

Then delete the two now-redundant `<div class="field">` blocks for "Overall status" and "Trend vs last week" (they were lines 132–149 before Task 5).

- [ ] **Step 3: Confirm before replacing an existing review**

In `draftWithAi()`, insert immediately after `if (!selected) return;`:

```ts
    if (
      (editObs || editNext) &&
      !confirm("Replace this week's review with a new AI draft?")
    )
      return;
```

- [ ] **Step 4: Add the pill styles**

Delete the now-unused `.opt` rule from the `<style>` block — the status buttons it styled were removed in Step 2 — then add:

```css
  button.pill {
    cursor: pointer;
  }
  .pill.unset {
    border-style: dashed;
    background: none;
    color: var(--text-muted);
  }
  .statuspick {
    display: inline-flex;
    gap: 0.3rem;
  }
  /* Global `select` is width:100%, which would blow out the header row. */
  .weekhead select {
    width: auto;
  }
```

- [ ] **Step 5: Verify**

```bash
npm run format && npm run check && npm run lint && npm test
```

Expected: 0 errors from svelte-check; eslint and prettier pass; vitest passes.

By hand, walk the spec's verification list:
1. A week with a saved plain-text review renders as paragraphs, no stray headings.
2. `✨ Draft with AI` on an empty week returns sectioned markdown; `###` renders as accent labels; Analysis opens with a bolded sentence; it saves and shows `Saved ✓`.
3. Draft on a week that already has a review → confirm dialog; cancelling leaves the saved text untouched.
4. With 10+ tracked weeks, the draft cites earlier weeks by number and every cited week exists.
5. Tap the status pill → expands to G/A/R → pick → collapses, saves, and the week chip in the list updates.
6. ✎ on Key observations → textarea with the full field; Next steps still rendered below; Done → saves and re-renders.
7. Switching weeks mid-edit lands on the rendered view with controls collapsed.
8. The first tracked week drafts without error (empty `history`).
9. A week with no status shows the dashed "Set status" pill with the suggestion beside it, and does **not** save a status until one is picked.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/routes/weekly/+page.svelte
git commit -m "feat(weekly): inline status/trend pills and confirm before redrafting"
```

---

## Done when

- `backend/.venv/bin/python -m pytest` passes from `backend/`.
- `backend/.venv/bin/python -m ruff check app tests` reports no issues.
- `npm test && npm run check && npm run lint` pass from `frontend/`.
- All nine manual checks in Task 6 Step 5 pass against a real week of data.
