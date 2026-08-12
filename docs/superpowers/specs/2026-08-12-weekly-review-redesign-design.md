# Design: Weekly review — structured AI output and document presentation

**Date:** 2026-08-12
**Status:** Approved (design), pending implementation plan

## Problem

The weekly page's **Key observations** and **Next steps** come back from the AI
drafter as a flat paragraph of prose. Outside NerveTrack, feeding the same
tracking data to Claude produces a sectioned, formatted review — headings, a
bolded thesis, comparisons to earlier weeks — that is far easier to read and act
on. The user wants that inside the app.

Two things stand between here and there, and only one of them is presentation:

1. **The drafter is asked for the wrong thing.** `app/services/llm.py:107` asks
   for "a retrospective narrative in the user's established concise style" with
   no mention of headings, sections, or structure.
2. **The drafter cannot see history.** `get_week_bundle`
   (`app/services/weekly.py:169`) returns only the selected week, and unlike
   `stream_chat`, `draft_weekly` runs without tools. Lines like "matching the
   best weeks in the program (W8, W11, W17)" are not possible from that input at
   any prompt quality.

Markdown *rendering* already works — `frontend/src/lib/markdown.ts` (marked +
DOMPurify) is wired into the weekly page at `+page.svelte:164-186`. There has
simply been little structure to render, and the rendered box is styled like a
form input rather than a document.

## Approach

Four changes, in dependency order: widen the bundle, rewrite the prompt, harden
the response parsing, then rebuild the page as a document with inline editing.
No database migration and no new stored fields — `key_observations` and
`next_steps` keep their meaning and simply hold richer markdown.

---

## Change 1 — Give the drafter program history

### `app/services/weekly.py`

`get_week_bundle` gains three keys, all derived from the existing
`list_weeks()` so no new queries are written:

```python
{
  "week_start": "2026-08-04",
  "week_end":   "2026-08-10",
  "program_week": 21,            # NEW — 1-based index among tracked weeks
  "summary": {...},              # unchanged
  "days":    [...],              # unchanged
  "history": [                   # NEW — every PRIOR week, metrics only
    {"program_week": 1, "week_start": "2026-03-24",
     "overall_status": "A", "trend_vs_last_week": "Same",
     "strengthening_sessions": 2, "avg_pain_episodes_per_day": "1.4",
     "avg_tingling_level": "2.1", "worst_pain": "4.0", "days_logged": 7,
     "green_days": 2, "amber_days": 4, "red_days": 1,
     "suggested_status": "A", "sitting_minutes": 1920,
     "standing_minutes": 600},
    ...
  ],
  "recent_reviews": [            # NEW — narrative continuity, most recent first
    {"program_week": 20, "week_start": "2026-07-28",
     "key_observations": "...", "next_steps": "..."}
  ]
}
```

Implementation sketch:

```python
weeks = sorted(list_weeks(db, user_id), key=lambda w: w.week_start)  # asc
numbers = {w.week_start: i for i, w in enumerate(weeks, start=1)}
prior = [w for w in weeks if w.week_start < week_start]

program_week = numbers.get(week_start, len(weeks) + 1)
history = [
    {"program_week": numbers[w.week_start],
     "week_start": w.week_start.isoformat(),
     "overall_status": w.overall_status,
     "trend_vs_last_week": w.trend_vs_last_week,
     **w.computed.model_dump(mode="json")}
    for w in prior
]
reviewed = [w for w in prior if w.key_observations][-3:]   # 3 most recent
recent_reviews = [
    {"program_week": numbers[w.week_start],
     "week_start": w.week_start.isoformat(),
     "key_observations": w.key_observations,
     "next_steps": w.next_steps}
    for w in reversed(reviewed)                            # most recent first
]
```

Notes:

- `list_weeks` returns descending; sort ascending first so week numbering runs
  oldest-to-newest. Week 1 is the first week containing any logged entry.
- `program_week` falls back to `len(weeks) + 1` when the requested week sits
  beyond the logged range, so a freshly-started week still numbers sensibly.
- `w.computed.model_dump(mode="json")` renders `Decimal` fields as strings,
  which `json.dumps(..., default=str)` in the prompt already tolerates.
- **No cap on `history`.** At ~15 numbers per week, a full year is roughly
  3–4k tokens. If it ever becomes a problem the fix is a slice, not a design
  change — do not build one now.
- `recent_reviews` is capped at 3 and includes only weeks with saved
  observations. Everything is user-scoped because `list_weeks` already is.

---

## Change 2 — Ask for structured markdown

### `app/services/llm.py`

`draft_weekly`'s prompt is rewritten. Section structure is **guided, not
fixed**: the prompt offers a menu and instructs the model to use only what the
week's data supports, so a quiet week produces two sections rather than four
padded ones.

```
Draft this week's review from the JSON data below.

Write both fields as markdown. Structure the key observations with `###`
headings drawn from this menu, using ONLY the sections this week's data
supports — skip any you would have to pad:

  ### The week at a glance   — the headline numbers and how they compare
  ### What stood out         — the notable events, sessions, and symptoms
  ### Analysis               — why it matters
  ### Watch-outs             — anything to keep an eye on

Open Analysis with a single bolded sentence naming the most significant thing
in this week's data, then argue it from the sequence of days: name the days,
the numbers, and the exercises involved. Where `history` supports it, compare
against earlier program weeks by number (e.g. "matching W8, W11, W17"). Never
cite a week that is not present in `history`, and never invent a number.

Aim for 350-500 words of key observations and 100-150 words of next steps.
Write next steps as a short lead sentence followed by a numbered list.

Respond in exactly this format, with no prose outside it:

<<<KEY_OBSERVATIONS>>>
(markdown)
<<<NEXT_STEPS>>>
(markdown)

DATA:
{json}
```

The existing `SYSTEM_PROMPT` and `records_context` injection are unchanged.

---

## Change 3 — Parse with delimiters, not JSON

The current parser is `json.loads(raw[raw.find("{"):raw.rfind("}") + 1])` with
no error handling (`llm.py:120`), so a single unescaped newline raises and the
endpoint 500s. Change 2 starts demanding hundreds of words of multi-line
markdown, which is precisely where models mis-escape JSON string values.
Delimiters cannot be broken by newlines.

```python
KEY_MARKER = "<<<KEY_OBSERVATIONS>>>"
NEXT_MARKER = "<<<NEXT_STEPS>>>"


def _parse_draft(raw: str) -> WeeklyDraftResponse:
    """Split a delimited draft. Never raises — a malformed reply still yields
    something the user can edit rather than a 500."""
    if KEY_MARKER in raw:
        _, rest = raw.split(KEY_MARKER, 1)
        if NEXT_MARKER in rest:
            obs, nxt = rest.split(NEXT_MARKER, 1)
            return WeeklyDraftResponse(
                key_observations=obs.strip(), next_steps=nxt.strip()
            )
        return WeeklyDraftResponse(key_observations=rest.strip(), next_steps="")
    return WeeklyDraftResponse(key_observations=raw.strip(), next_steps="")
```

`WeeklyDraftResponse` and the `/ai/weekly-draft/{week_start}` route are
unchanged.

---

## Change 4 — The weekly page as a document

### `frontend/src/routes/weekly/+page.svelte`

The selected-week card stops being a form containing two rendered boxes and
becomes a document with controls embedded in it.

**Header row.** Date range, then a status pill, a trend pill, and the save
indicator:

- **Status pill** shows `G`/`A`/`R` tinted with the existing `status-*` classes.
  Tapping expands it in place into the three choices; picking one collapses it
  and saves. When unset, it renders as a dashed "Set status" pill with the
  computed `suggested_status` as a muted hint beside it.
- **Trend pill** shows the saved trend, or "Set trend" when empty. Tapping
  swaps it for the existing `<select>`; changing it saves and collapses.
- **Save indicator** reuses the Today page's idiom (`+page.svelte:160`):
  `Saving… / Saved ✓`.

**Metrics strip.** The three-column `.metrics` grid is replaced by one wrapping
row on `--surface-2` at `--r-pill`, each item a bold value with a muted label:
sessions · avg episodes/day · avg tingling · worst pain · days logged · sitting
hours · G/A/R days.

**Review body.** Two blocks — Key observations, then Next steps — rendered with
the existing `renderMarkdown`, separated by a `--border` rule. Prose sits at
`max-width: 62ch` with `line-height: 1.7`. Markdown `h3` is styled as the
section label: Space Grotesk, uppercase, `letter-spacing: 0.05em`, `--accent`,
small. `h2` and `h4` get the same treatment as a fallback in case the model
picks a different level. A `**bolded**` opening sentence needs no special rule —
`<strong>` is enough.

**Editing (edit-in-place, whole field).** Each block carries a muted ✎ at its
top-right. Clicking swaps *that block* — the entire stored field, not a single
`###` section — for a monospace textarea, with the other block still rendered
around it. A **Done** button collapses it and saves. Editing the whole field
avoids splitting and reassembling markdown around headings, which would break on
renamed headings, duplicate headings, or text before the first heading.

**Empty state.** With no text saved, a block shows a muted line — "No review yet
— ✨ Draft with AI, or ✎ to write one" — rather than an empty bordered box.

**Saving.** The **Save** button is removed. `save()` runs immediately on each
of: status pick, trend change, Done on either textarea, and an accepted AI
draft. `saveState` drives the header indicator.

No debounce. The Today page debounces because it has free-typing inputs
(`+page.svelte:85-102`); every control here is a discrete one-shot event, so a
timer would coalesce nothing while opening a window in which a week switch
lands the in-flight save on the wrong week. `save()` still captures its target
`week_start` and re-checks it after the `await` before writing back `selected`
and `saveState`, because the request itself is a window.

**Drafting.** `✨ Draft with AI` moves to the foot of the review. If either
field already has content it confirms first — "Replace this week's review with a
new AI draft?" — so a stray tap cannot silently destroy an edited week. On
accept, both fields are replaced, both blocks return to rendered view, and the
draft saves like any other change. The existing 409 handling ("Configure a model
in Settings first.") is kept.

**Week switching.** `select(w)` continues to reset the edit toggles, and also
resets the status/trend expansion state and `saveState`.

**State changes:** drop `message` as a save-status carrier; add
`saveState: 'idle' | 'saving' | 'saved'`, `editingStatus`, `editingTrend`, and a
debounce timer. `editingObs` / `editingNext` are retained as-is.

**Accessibility:** the ✎ controls get `aria-label`s ("Edit key observations"),
the status pill gets `aria-expanded`, and each textarea keeps an associated
label even when the visible label is the section heading.

### Legacy content

Reviews saved before this change are plain prose with no headings. They render
as ordinary paragraphs inside the new document styling. No migration, no
backfill.

---

## Tests

**Backend**

- `tests/test_weekly.py` — `get_week_bundle` includes `program_week` numbered
  from the first logged week; `history` contains prior weeks only (never the
  selected week or later ones) with correct numbering; `history` is empty for
  the first tracked week; `recent_reviews` caps at 3, includes only weeks with
  saved `key_observations`, and is ordered most-recent-first; another user's
  weeks never appear.
- `tests/test_llm.py` — replace `test_draft_weekly_parses_json` (line 97) with
  delimiter coverage: a well-formed delimited reply splits into both fields;
  markdown containing newlines and `###` headings survives intact; a reply with
  no markers returns the whole text as `key_observations` with empty
  `next_steps` instead of raising.

**Frontend**

- `src/lib/markdown.test.ts` already covers heading, bold, and list rendering
  plus sanitisation — no change needed.
- The page change is view wiring, verified manually (below).

---

## Out of scope

- No new stored fields and no migration — no separate `analysis` column.
- No markdown toolbar or WYSIWYG; editing stays a plain textarea.
- No per-section editing of markdown slices.
- No draft staging / "Keep or Discard" flow — the confirm dialog covers it.
- No Settings control for review depth or length.
- No tool-calling loop for `draft_weekly`; it stays a single completion.
- No change to the chat page, the daily entry pages, or `records_context`.

## Verification

1. Select a week with a saved plain-text review → renders as paragraphs in the
   new document styling, no stray headings.
2. `✨ Draft with AI` on a week with no review → returns sectioned markdown;
   `###` headings render as accent section labels; Analysis opens with a bolded
   sentence; the draft saves and the indicator reads `Saved ✓`.
3. Draft on a week that already has a review → confirm dialog appears;
   cancelling leaves the saved text untouched.
4. On a user with 10+ tracked weeks, the draft cites earlier weeks by number and
   every cited week exists.
5. Tap the status pill → expands to G/A/R → pick → collapses, saves, and the
   week chip in the list updates.
6. ✎ on Key observations → textarea holding the full field, Next steps still
   rendered below; Done → saves and re-renders.
7. Switch weeks mid-edit → lands on the rendered view with controls collapsed.
8. First tracked week drafts without error (`history` empty).
