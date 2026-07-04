# Timer page: combined display + 24-hour timeline bar

**Date:** 2026-07-04
**Status:** Approved design, ready for implementation planning
**Area:** `frontend/src/routes/timer/+page.svelte` and supporting `frontend/src/lib`

## Problem

The timer page shows the posture timer and the tingling timer as two fully
separate sections, each with its own live-clock display card. The tingling
section sits far down the page, below the posture totals. This splits attention
and buries the tingling readout. There is also no view that plots what happened
*when* across the day — the only proportional view is the `RatioBar` (posture
totals), which shows how much time, not when.

## Goals

1. **Merge the two live displays into one card.** Posture stays the primary,
   full-size clock. When a tingling interval is running, its readout appears
   beneath it, smaller, in the same card.
2. **Add a 24-hour timeline bar** (midnight → midnight) that plots posture
   intervals and tingling intervals at their real clock positions.
3. **Reorder the page** so the timeline sits directly under the controls, and
   move the posture totals lower.

## Non-goals

- No changes to the backend, data model, or API. This is a frontend
  presentation change built entirely from data the two stores already expose.
- No changes to how intervals are created, edited, or deleted.
- No new colors beyond a single tingling accent (violet) already needed to keep
  tingling visually distinct from the four postures.

## Decisions (locked with the user)

- Timeline bar style: **Option A — two stacked tracks** (posture strip on top,
  thin tingling strip beneath, shared hour axis).
- Controls: **one merged control panel** (posture buttons + tingling
  level/Start/Stop in a single card, divided by a dashed rule).
- Combined display tingling readout: **`Tingling · {elapsed} · level {n}`**
  (level shown inline).
- Both interval tables (posture, tingling) land at the bottom of the page rather
  than being merged into one table.

## New page order (top → bottom)

| # | Card | Visibility |
|---|------|-----------|
| 1 | Date bar | always |
| 2 | Combined display box | today only |
| 3 | Merged control panel | today only |
| 4 | 24-hour timeline bar | always (any viewed day) |
| 5 | Posture totals (4-up grid + Sit:Stand + `RatioBar`) | always |
| 6 | Posture interval table ("Today's timeline" / "Timeline — {date}") | always |
| 7 | Tingling interval table | any viewed day, when it has rows |

The combined display and merged controls remain gated on `isToday`, exactly as
the posture display and controls are today. The timeline bar renders for any
viewed day because it is historical.

## Component design

### 1. Combined display box

A single `.card.display` replaces the two separate display cards.

- **Posture region (unchanged):** posture name (uppercase, muted), the
  full-size clock (`formatDuration(store.elapsed)`) colored by
  `postureColor(running.posture)`, optional label line. When nothing is running,
  the existing "Not tracking / 00s" muted state.
- **Tingling region (additive):** rendered only when `tingle.running` is set.
  A thin divider rule, then a smaller readout:
  `Tingling · {formatDuration(tingle.elapsed)} · level {tingle.running.level}`,
  tinted with the tingling accent. When tingling is not running, this region is
  absent and the box is posture-only — no layout jump.
- The 45-minute sitting **nudge** stays in this card, unchanged.

The card keeps the `running` border-accent treatment when the posture timer is
running.

### 2. Merged control panel

A single `.card` holds both control groups:

- Posture: the optional-label input, the 2×2 posture button grid, and the
  full-width Stop button — unchanged behavior (`pick`, `stop`).
- A dashed `border-top` divider.
- Tingling: a small "Tingling timer" caption with the violet dot, the
  `level (0–10)` number input, and Start / Stop buttons — unchanged behavior
  (`startTingle`, `stopTingle`). Start disabled when level is null or tingling
  already running; Stop disabled when not running.

No behavior changes to any handler — only their DOM location.

### 3. 24-hour timeline bar (Option A)

A new reusable component: **`TimelineBar.svelte`**, with geometry math split
into a pure, unit-tested helper **`timelineBar.ts`** — mirroring the existing
`RatioBar.svelte` / `ratio.ts` split.

**Inputs (props):**
- `intervals: Interval[]` — posture intervals for the viewed day.
- `tingling: TinglingInterval[]` — tingling intervals for the viewed day.
- `date: string` — the viewed ISO date.
- `now: number` — current epoch ms (for the running edge + `now` marker),
  passed from the store tick so the bar stays live.

**Layout:**
- **Posture strip (top):** contiguous colored segments across the 24h axis, each
  positioned by its start/end minute-of-day. Segment width is proportional to
  duration. A running interval extends to `now`. The portion of the day after
  the last logged point renders empty (transparent over the track background).
- **Tingling strip (below):** a thin track; each tingling interval is an
  absolutely-positioned violet block at its start→end position. Sparse by
  nature — gaps read as "no tingling". A running tingling interval extends to
  `now`.
- **Hour axis:** ticks/labels at 12a · 6a · 12p · 6p · 12a (0 / 25 / 50 / 75 /
  100 %).
- **`now` marker:** a thin accent vertical line at the current time — shown only
  when the viewed day is today.
- **Legend:** the four posture colors + tingling.
- **Tooltips:** each segment carries a `title` with label and start–end times.

**Geometry helper (`timelineBar.ts`):** pure functions that convert an interval
list into positioned segments as percentages of the day. Handles:
- minute-of-day from a naive-UTC ISO timestamp, in local time (consistent with
  the page's existing `fmtTime` / time helpers);
- the running interval's live end (`now`);
- clamping segments to the [00:00, 24:00) window of the viewed day (a segment
  that started before midnight or a running interval that has crossed into the
  next day is clamped to the day bounds);
- returning `{ leftPct, widthPct, key, colorVar/level, tooltip }` for each
  segment for both posture and tingling.

Keeping this logic pure and separate makes the cross-midnight and running-edge
cases unit-testable without a DOM, matching how `ratio.ts` is tested.

### 4. Totals and tables

- The posture **totals card** (4-up grid, Sit:Stand ratio, `RatioBar`) is
  unchanged in content; it simply moves below the timeline bar.
- The **posture interval table** is unchanged (edit time / label / delete).
- The **tingling interval table** moves out of the (now-removed) tingling
  section to the bottom of the page. Its content and handlers (`tingle.remove`,
  time formatting) are unchanged. It shows for any viewed day when it has rows,
  consistent with the posture interval table (which already renders for any
  day), since date navigation now loads the tingling store per-day.

## Data flow

No new data sources. `TimerStore` already exposes `running`, `intervals`,
`totals`, `elapsed`, `now`, `date`. `TinglingTimerStore` already exposes
`running`, `intervals`, `elapsed`, `now`, `date`. The timeline bar is a pure
function of `store.intervals`, `tingle.intervals`, `store.date`, and a shared
`now` tick. Both stores already tick once per second; the bar re-derives on each
tick via Svelte reactivity.

## Edge cases

- **Empty day:** no posture intervals → posture strip is the empty track
  background; tingling strip empty; axis and legend still render. A muted "No
  intervals yet" remains in the interval table as today.
- **Today, partial:** future region after `now` is empty; `now` marker present.
- **Past day:** full logged day; no `now` marker; no combined display/controls
  (today-gated).
- **Running interval at view time:** posture and/or tingling running block
  extends to `now`.
- **Cross-midnight interval:** clamped to the viewed day's [00:00, 24:00)
  bounds by the geometry helper.
- **Overlapping tingling and posture:** expected and fine — they are separate
  strips, so tingling never obscures posture.

## Testing

- `timelineBar.test.ts` (new): pure-function unit tests covering minute-of-day
  conversion, proportional widths, running-edge extension to `now`,
  cross-midnight clamping, empty input, and the today-vs-past `now` marker flag.
- Existing `ratio.test.ts`, `time.test.ts`, `timeline.test.ts` continue to pass
  unchanged.
- Manual verification: run the app, view today with/without a running posture
  and/or tingling interval, view a past day, and confirm order, the combined
  display states, and the bar in both light and dark themes.

## Files touched (anticipated)

- `frontend/src/lib/timelineBar.ts` — new pure geometry helper.
- `frontend/src/lib/timelineBar.test.ts` — new unit tests.
- `frontend/src/lib/components/TimelineBar.svelte` — new component.
- `frontend/src/routes/timer/+page.svelte` — reorder cards, merge the two
  display cards into one, merge the two control groups into one, mount
  `TimelineBar`, relocate totals and the tingling table.

No changes outside `frontend/`.

## Reference

Interactive mockups (built on the app's real theme) used to agree this design:
board 1 full page, board 2 combined display + merged controls, board 3 the three
timeline options with Option A chosen.
