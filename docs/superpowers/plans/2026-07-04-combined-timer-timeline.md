# Combined Timer Display + 24h Timeline Bar Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Merge the posture and tingling timer displays into one card, add a midnight-to-midnight 24-hour timeline bar (posture + tingling), and reorder the timer page so totals sit lower.

**Architecture:** A new pure helper `timelineBar.ts` converts posture/tingling intervals into positioned segments (percent of day), mirroring the existing `ratio.ts` / `RatioBar.svelte` split. A new `TimelineBar.svelte` renders two stacked strips (posture on top, tingling beneath) with an hour axis, legend, and a live `now` marker. The timer page (`timer/+page.svelte`) is recomposed: one combined display card, one merged control card, the timeline bar, then totals and the interval tables.

**Tech Stack:** SvelteKit (Svelte 5 runes), TypeScript, Vitest. Frontend only — no backend/API/data-model changes.

## Global Constraints

- All work is inside `frontend/`. No backend, API, or data-model changes.
- Timestamps from the API are naive-UTC ISO strings; parse with `Date.parse(iso + 'Z')` and format for display with `new Date(iso + 'Z').toLocaleTimeString(...)` — matching the existing `fmtTime` / `intervalSeconds` convention.
- Tingling uses a single dedicated accent color `--tingle` (violet), never a posture color.
- Posture color mapping is fixed: Sitting=`--bad`, Standing=`--good`, Lying=`--rest`, Walking=`--move` (via `postureColor()`).
- Test runner: `npm run test` (vitest, run mode). Type/compile check: `npm run check`. Run all commands from `frontend/`.
- Pure logic lives in `lib/*.ts` with a sibling `*.test.ts`; components live in `lib/components/`.

---

## File Structure

- **Create** `frontend/src/lib/timelineBar.ts` — pure geometry: interval → percent-of-day segments; posture/tingling segment builders; `now` marker position. One responsibility: turn intervals into positioned bar segments.
- **Create** `frontend/src/lib/timelineBar.test.ts` — unit tests for the geometry helper.
- **Create** `frontend/src/lib/components/TimelineBar.svelte` — presentational component that renders the two strips + axis + legend from the helper output.
- **Modify** `frontend/src/app.css` — add the `--tingle` token to the dark (`:root`) and light theme blocks.
- **Modify** `frontend/src/routes/timer/+page.svelte` — combine the two display cards, merge the two control groups, mount `TimelineBar`, reorder totals below it, relocate the tingling table to the bottom, and load the tingling store on date navigation.

---

## Task 1: Pure timeline geometry helper (`timelineBar.ts`)

**Files:**
- Create: `frontend/src/lib/timelineBar.ts`
- Test: `frontend/src/lib/timelineBar.test.ts`

**Interfaces:**
- Consumes: `Interval`, `TinglingInterval`, `Posture` from `$lib/types`.
- Produces:
  - `MINUTES_PER_DAY: number` (= 1440)
  - `localDayStartMs(date: string): number` — local-midnight epoch ms for `"YYYY-MM-DD"`.
  - `interface BarGeometry { leftPct: number; widthPct: number; startMs: number; endMs: number }`
  - `intervalToSegment(startISO: string, endISO: string | null, dayStart: number, now: number): BarGeometry | null`
  - `interface PostureBarSegment extends BarGeometry { posture: Posture }`
  - `postureSegments(intervals: Interval[], dayStart: number, now: number): PostureBarSegment[]`
  - `interface TinglingBarSegment extends BarGeometry { level: number }`
  - `tinglingSegments(intervals: TinglingInterval[], dayStart: number, now: number): TinglingBarSegment[]`
  - `nowPct(dayStart: number, now: number): number` — clamped to `[0, 100]`.

- [ ] **Step 1: Write the failing tests**

Create `frontend/src/lib/timelineBar.test.ts`:

```ts
import { describe, expect, it } from 'vitest';
import {
  MINUTES_PER_DAY,
  localDayStartMs,
  intervalToSegment,
  postureSegments,
  tinglingSegments,
  nowPct
} from './timelineBar';
import type { Interval, TinglingInterval } from './types';

// All geometry tests use dayStart = epoch 0 so `Date.parse(iso + 'Z')` (UTC)
// yields deterministic positions independent of the test runner's timezone.
const DAY0 = 0;
const H = 3_600_000; // one hour in ms

describe('MINUTES_PER_DAY', () => {
  it('is 1440', () => expect(MINUTES_PER_DAY).toBe(1440));
});

describe('localDayStartMs', () => {
  it('returns local midnight for the date', () => {
    const d = new Date(localDayStartMs('2026-07-04'));
    expect(d.getFullYear()).toBe(2026);
    expect(d.getMonth()).toBe(6); // July, 0-indexed
    expect(d.getDate()).toBe(4);
    expect(d.getHours()).toBe(0);
    expect(d.getMinutes()).toBe(0);
  });
});

describe('intervalToSegment', () => {
  it('positions a completed interval by start and end', () => {
    const g = intervalToSegment('1970-01-01T06:00:00', '1970-01-01T12:00:00', DAY0, 0)!;
    expect(g.leftPct).toBeCloseTo(25);
    expect(g.widthPct).toBeCloseTo(25);
    expect(g.startMs).toBe(6 * H);
    expect(g.endMs).toBe(12 * H);
  });

  it('extends a running interval to now', () => {
    const g = intervalToSegment('1970-01-01T06:00:00', null, DAY0, 9 * H)!;
    expect(g.leftPct).toBeCloseTo(25);
    expect(g.widthPct).toBeCloseTo(12.5);
    expect(g.endMs).toBe(9 * H);
  });

  it('clamps a running interval that crosses midnight to end of day', () => {
    const g = intervalToSegment('1970-01-01T22:00:00', null, DAY0, 25 * H)!;
    expect(g.leftPct).toBeCloseTo(91.6667);
    expect(g.widthPct).toBeCloseTo(8.3333);
    expect(g.endMs).toBe(MINUTES_PER_DAY * 60_000);
  });

  it('clamps a segment that started before midnight to start of day', () => {
    const g = intervalToSegment('1969-12-31T23:00:00', '1970-01-01T01:00:00', DAY0, 0)!;
    expect(g.leftPct).toBeCloseTo(0);
    expect(g.widthPct).toBeCloseTo(4.1667);
    expect(g.startMs).toBe(0);
  });

  it('returns null when the interval has no width within the day', () => {
    expect(intervalToSegment('1969-12-31T22:00:00', '1969-12-31T23:00:00', DAY0, 0)).toBeNull();
  });
});

describe('postureSegments', () => {
  it('maps intervals to segments carrying their posture, dropping empties', () => {
    const intervals = [
      { id: 'a', posture: 'sitting', started_at: '1970-01-01T00:00:00', ended_at: '1970-01-01T06:00:00', duration_seconds: 21600 },
      { id: 'b', posture: 'standing', started_at: '1970-01-01T06:00:00', ended_at: null, duration_seconds: null }
    ] as unknown as Interval[];
    const segs = postureSegments(intervals, DAY0, 12 * H);
    expect(segs.map((s) => s.posture)).toEqual(['sitting', 'standing']);
    expect(segs[0].widthPct).toBeCloseTo(25);
    expect(segs[1].widthPct).toBeCloseTo(25);
  });
});

describe('tinglingSegments', () => {
  it('maps intervals to segments carrying their level', () => {
    const intervals = [
      { id: 't', level: 6, started_at: '1970-01-01T09:00:00', ended_at: '1970-01-01T10:00:00', duration_seconds: 3600 }
    ] as unknown as TinglingInterval[];
    const segs = tinglingSegments(intervals, DAY0, 0);
    expect(segs).toHaveLength(1);
    expect(segs[0].level).toBe(6);
    expect(segs[0].leftPct).toBeCloseTo(37.5);
  });
});

describe('nowPct', () => {
  it('returns the percent of day for now', () => {
    expect(nowPct(DAY0, 6 * H)).toBeCloseTo(25);
  });
  it('clamps below 0 and above 100', () => {
    expect(nowPct(DAY0, -H)).toBe(0);
    expect(nowPct(DAY0, 30 * H)).toBe(100);
  });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd frontend && npm run test -- timelineBar`
Expected: FAIL — `Failed to resolve import "./timelineBar"` / functions not defined.

- [ ] **Step 3: Write the implementation**

Create `frontend/src/lib/timelineBar.ts`:

```ts
// Pure geometry for the 24-hour timeline bar. Converts posture/tingling
// intervals into segments positioned as percentages of the day. Kept
// dependency-free and DOM-free so the cross-midnight and running-edge cases
// are unit-testable, mirroring ratio.ts.

import type { Interval, Posture, TinglingInterval } from './types';

export const MINUTES_PER_DAY = 1440;
const MS_PER_MINUTE = 60_000;
const MS_PER_DAY = MINUTES_PER_DAY * MS_PER_MINUTE;

/** Local-midnight epoch ms for a "YYYY-MM-DD" date string. */
export function localDayStartMs(date: string): number {
  const [y, m, d] = date.split('-').map(Number);
  return new Date(y, m - 1, d).getTime();
}

export interface BarGeometry {
  leftPct: number;
  widthPct: number;
  startMs: number;
  endMs: number;
}

/**
 * Position an interval within the [dayStart, dayStart + 24h) window as
 * percentages of the day. A running interval (ended_at null) ends at `now`.
 * Both edges are clamped to the day bounds; returns null when no visible
 * width remains within the day.
 */
export function intervalToSegment(
  startISO: string,
  endISO: string | null,
  dayStart: number,
  now: number
): BarGeometry | null {
  const dayEnd = dayStart + MS_PER_DAY;
  const rawStart = Date.parse(startISO + 'Z');
  const rawEnd = endISO != null ? Date.parse(endISO + 'Z') : now;
  const startMs = Math.max(rawStart, dayStart);
  const endMs = Math.min(rawEnd, dayEnd);
  if (endMs <= startMs) return null;
  const leftPct = ((startMs - dayStart) / MS_PER_DAY) * 100;
  const widthPct = ((endMs - startMs) / MS_PER_DAY) * 100;
  return { leftPct, widthPct, startMs, endMs };
}

export interface PostureBarSegment extends BarGeometry {
  posture: Posture;
}

export function postureSegments(
  intervals: Interval[],
  dayStart: number,
  now: number
): PostureBarSegment[] {
  const out: PostureBarSegment[] = [];
  for (const iv of intervals) {
    const g = intervalToSegment(iv.started_at, iv.ended_at, dayStart, now);
    if (g) out.push({ ...g, posture: iv.posture });
  }
  return out;
}

export interface TinglingBarSegment extends BarGeometry {
  level: number;
}

export function tinglingSegments(
  intervals: TinglingInterval[],
  dayStart: number,
  now: number
): TinglingBarSegment[] {
  const out: TinglingBarSegment[] = [];
  for (const iv of intervals) {
    const g = intervalToSegment(iv.started_at, iv.ended_at, dayStart, now);
    if (g) out.push({ ...g, level: iv.level });
  }
  return out;
}

/** Position of the `now` marker as a percentage of the day, clamped to [0, 100]. */
export function nowPct(dayStart: number, now: number): number {
  const pct = ((now - dayStart) / MS_PER_DAY) * 100;
  return Math.min(100, Math.max(0, pct));
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd frontend && npm run test -- timelineBar`
Expected: PASS — all cases in `timelineBar.test.ts` green.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/timelineBar.ts frontend/src/lib/timelineBar.test.ts
git commit -m "feat(timer): pure geometry helper for 24h timeline bar"
```

---

## Task 2: `TimelineBar.svelte` component + `--tingle` token

**Files:**
- Modify: `frontend/src/app.css` (add `--tingle` to dark `:root` and the light theme block)
- Create: `frontend/src/lib/components/TimelineBar.svelte`

**Interfaces:**
- Consumes: `postureSegments`, `tinglingSegments`, `nowPct`, `localDayStartMs` from `$lib/timelineBar`; `postureColor` from `$lib/posture`; `POSTURE_LABEL`, `POSTURES`, `todayISO` from `$lib/time`; `Interval`, `TinglingInterval` from `$lib/types`.
- Produces: a component with props `{ intervals: Interval[]; tingling: TinglingInterval[]; date: string; now: number }`.

- [ ] **Step 1: Add the `--tingle` token to `app.css`**

In `frontend/src/app.css`, the dark palette is the top `:root` block (contains `--move: #4bb0d6;`). Add the tingling accent right after the `--move` line in that block:

```css
  --tingle: #b184e6;
```

The light theme block contains `--move: #2b93bd;`. Add right after it in that block:

```css
  --tingle: #7b52c4;
```

Verify both were added:

Run: `cd frontend && grep -n "\-\-tingle" src/app.css`
Expected: two lines — `#b184e6` (dark) and `#7b52c4` (light).

- [ ] **Step 2: Create the component**

Create `frontend/src/lib/components/TimelineBar.svelte`:

```svelte
<script lang="ts">
  import type { Interval, TinglingInterval } from '$lib/types';
  import { postureSegments, tinglingSegments, nowPct, localDayStartMs } from '$lib/timelineBar';
  import { postureColor } from '$lib/posture';
  import { POSTURE_LABEL, POSTURES, todayISO } from '$lib/time';

  let {
    intervals,
    tingling,
    date,
    now
  }: { intervals: Interval[]; tingling: TinglingInterval[]; date: string; now: number } = $props();

  const dayStart = $derived(localDayStartMs(date));
  const pSegs = $derived(postureSegments(intervals, dayStart, now));
  const tSegs = $derived(tinglingSegments(tingling, dayStart, now));
  const isToday = $derived(date === todayISO());
  const nowLeft = $derived(nowPct(dayStart, now));
  const hasTingling = $derived(tSegs.length > 0);

  const TICKS = [
    { pct: 0, label: '12a', cls: 'first' },
    { pct: 25, label: '6a', cls: '' },
    { pct: 50, label: '12p', cls: '' },
    { pct: 75, label: '6p', cls: '' },
    { pct: 100, label: '12a', cls: 'last' }
  ];

  function fmtMs(ms: number): string {
    return new Date(ms).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  }
</script>

<div class="tl">
  <div class="tl-caps">{isToday ? 'Timeline · today' : `Timeline · ${date}`}</div>

  <div class="tl-body">
    <div class="pbar">
      {#each pSegs as s (s.startMs)}
        <div
          class="pseg"
          style="left:{s.leftPct}%; width:{s.widthPct}%; background:{postureColor(s.posture)}"
          title="{POSTURE_LABEL[s.posture]} {fmtMs(s.startMs)}–{fmtMs(s.endMs)}"
        ></div>
      {/each}
    </div>
    {#if isToday}<div class="nowline" style="left:{nowLeft}%"></div>{/if}
  </div>

  <div class="tstrip">
    {#each tSegs as s (s.startMs)}
      <div
        class="tseg"
        style="left:{s.leftPct}%; width:{s.widthPct}%"
        title="Tingling level {s.level} · {fmtMs(s.startMs)}–{fmtMs(s.endMs)}"
      ></div>
    {/each}
  </div>

  <div class="axis">
    {#each TICKS as t}<div class="tick {t.cls}" style="left:{t.pct}%">{t.label}</div>{/each}
  </div>

  <div class="tl-legend">
    {#each POSTURES as p}
      <span><i style="background:{postureColor(p)}"></i>{POSTURE_LABEL[p]}</span>
    {/each}
    {#if hasTingling}<span><i style="background:var(--tingle)"></i>Tingling</span>{/if}
  </div>
</div>

<style>
  .tl {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }
  .tl-caps {
    text-transform: uppercase;
    letter-spacing: 0.09em;
    font-size: 0.72rem;
    color: var(--text-muted);
    font-weight: 700;
  }
  .tl-body {
    position: relative;
  }
  .pbar {
    position: relative;
    width: 100%;
    height: 15px;
    border-radius: var(--r-sm);
    overflow: hidden;
    background: var(--surface-2);
  }
  .pseg {
    position: absolute;
    top: 0;
    bottom: 0;
  }
  .tstrip {
    position: relative;
    width: 100%;
    height: 9px;
    border-radius: var(--r-sm);
    background: var(--surface-2);
    overflow: hidden;
  }
  .tseg {
    position: absolute;
    top: 0;
    bottom: 0;
    background: var(--tingle);
    border-radius: 3px;
  }
  .nowline {
    position: absolute;
    top: -3px;
    bottom: -3px;
    width: 2px;
    background: var(--accent);
  }
  .axis {
    position: relative;
    height: 1rem;
  }
  .tick {
    position: absolute;
    top: 0;
    font-size: 0.66rem;
    color: var(--text-muted);
    font-variant-numeric: tabular-nums;
    transform: translateX(-50%);
  }
  .tick.first {
    transform: none;
  }
  .tick.last {
    transform: translateX(-100%);
  }
  .tl-legend {
    display: flex;
    flex-wrap: wrap;
    gap: 0.35rem 0.9rem;
    font-size: 0.74rem;
    color: var(--text-muted);
  }
  .tl-legend span {
    display: inline-flex;
    align-items: center;
    gap: 0.35rem;
  }
  .tl-legend i {
    width: 0.65rem;
    height: 0.65rem;
    border-radius: 3px;
    display: inline-block;
  }
</style>
```

- [ ] **Step 3: Type-check the component**

Run: `cd frontend && npm run check`
Expected: PASS — no type or Svelte errors. (`TimelineBar.svelte` is not yet imported anywhere; the check confirms it compiles.)

- [ ] **Step 4: Commit**

```bash
git add frontend/src/app.css frontend/src/lib/components/TimelineBar.svelte
git commit -m "feat(timer): TimelineBar component and --tingle token"
```

---

## Task 3: Recompose the timer page

**Files:**
- Modify: `frontend/src/routes/timer/+page.svelte`

**Interfaces:**
- Consumes: `TimelineBar.svelte` (props `intervals`, `tingling`, `date`, `now`); existing `TimerStore` / `TinglingTimerStore` fields and handlers (`store`, `tingle`, `label`, `tingleLevel`, `pick`, `stop`, `startTingle`, `stopTingle`, `running`, `nudge`, `totals`, `isToday`).
- Produces: the recomposed timer page (no new exports).

This task reorders the template, merges the two display cards into one, merges the two control groups into one, mounts `TimelineBar`, moves totals below the bar, relocates the tingling interval table to the bottom, and loads the tingling store on date navigation. It is a single UI deliverable; verification is `npm run check`, `npm run build`, and manual checks.

- [ ] **Step 1: Import `TimelineBar` and add a combined day loader**

In the `<script>` block of `frontend/src/routes/timer/+page.svelte`, add the import alongside the existing `RatioBar` import:

```ts
  import TimelineBar from '$lib/components/TimelineBar.svelte';
```

Then add a combined loader below the `onMount` / `onDestroy` block (near the other handlers) so date navigation loads both stores for the viewed day (today, the tingling store was only ever loaded once on mount):

```ts
  async function loadDay(date: string) {
    await Promise.all([store.load(date), tingle.load(date)]);
  }
```

- [ ] **Step 2: Wire the date bar to `loadDay`**

Replace the existing `.datebar` markup (the block starting `<div class="datebar card">`) with this version, which routes every date change through `loadDay`:

```svelte
<div class="datebar card">
  <button onclick={() => loadDay(shiftISODate(store.date, -1))} aria-label="previous day">‹</button>
  <div class="datepick">
    <input
      type="date"
      value={store.date}
      max={todayISO()}
      onchange={(e) => loadDay((e.currentTarget as HTMLInputElement).value)}
    />
    {#if !isToday}<button class="today" onclick={() => loadDay(todayISO())}>Today</button>{/if}
  </div>
  <button
    onclick={() => loadDay(shiftISODate(store.date, 1))}
    aria-label="next day"
    disabled={store.date >= todayISO()}>›</button
  >
</div>
```

- [ ] **Step 3: Replace the whole body between the date bar and the interval table**

Replace everything from the first `{#if isToday}` (the posture display block, currently `<div class="card display" ...>`) down to and including the standalone tingling `{#if isToday}` card (the block that ends just before `<div class="card">` containing `<h3>...timeline</h3>`) with the following. This is: combined display + merged controls (today only), then the always-on timeline bar, then the totals card.

```svelte
{#if isToday}
  <div class="card display" class:running={!!running}>
    {#if running}
      <div class="posture">{POSTURE_LABEL[running.posture]}</div>
      <div class="clock" style="color:{postureColor(running.posture)}">
        {formatDuration(store.elapsed)}
      </div>
      {#if running.label}<div class="muted">{running.label}</div>{/if}
    {:else}
      <div class="posture muted">Not tracking</div>
      <div class="clock muted">00s</div>
    {/if}
    {#if tingle.running}
      <div class="tingle-divider"></div>
      <div class="tingle-line">
        <span class="tingle-tag">Tingling</span>
        <span class="tingle-clock">{formatDuration(tingle.elapsed)}</span>
        <span class="tingle-lvl">· level {tingle.running.level}</span>
      </div>
    {/if}
    {#if nudge}
      <div class="nudge">You've been sitting for 45+ minutes — consider a stand break.</div>
    {/if}
  </div>

  <div class="card">
    <label>Optional label for next interval</label>
    <input bind:value={label} placeholder="e.g. work, meeting" />
    <div class="postures">
      {#each POSTURES as p}
        <button
          class="pbtn {running?.posture === p ? 'active' : ''}"
          style="--pc:var({postureColorVar(p)})"
          onclick={() => pick(p)}
        >
          {POSTURE_LABEL[p]}
        </button>
      {/each}
      <button class="stop" onclick={stop} disabled={!running}>Stop</button>
    </div>

    <div class="tingle-controls">
      <div class="tingle-caption"><span class="tingle-dot"></span>Tingling timer</div>
      <div class="row" style="align-items: flex-end; gap: 0.75rem">
        <div class="field" style="margin: 0; max-width: 8rem">
          <label>Level (0–10)</label>
          <input type="number" min="0" max="10" step="0.5" bind:value={tingleLevel} />
        </div>
        <button
          class="btn-primary"
          onclick={startTingle}
          disabled={tingleLevel === null || !!tingle.running}>Start</button
        >
        <button onclick={stopTingle} disabled={!tingle.running}>Stop</button>
      </div>
    </div>
  </div>
{/if}

<div class="card">
  <TimelineBar
    intervals={store.intervals}
    tingling={tingle.intervals}
    date={store.date}
    now={store.now}
  />
</div>

<div class="card totals">
  <div class="tgrid">
    {#each POSTURES as p}
      <div class="tcell">
        <div class="tlabel">{POSTURE_LABEL[p]}</div>
        <div class="tval">{formatMinutesish(totals[p])}</div>
      </div>
    {/each}
  </div>
  <div class="ratio">Sit : Stand = <strong>{sitStandRatio(totals)}</strong></div>
  <div style="margin-top: 0.9rem"><RatioBar {totals} showHeader={false} /></div>
</div>
```

- [ ] **Step 4: Move the tingling interval table to the bottom**

The standalone tingling card was removed in Step 3, but its interval table must survive. After the existing posture interval-table card (the block with `<h3>{isToday ? "Today's timeline" : ...}</h3>`), add a tingling interval-table card. Insert this immediately before the closing `<style>` tag's preceding content — i.e., as the last card in the template:

```svelte
{#if tingle.intervals.length > 0}
  <div class="card">
    <h3 style="margin-top: 0">Tingling intervals</h3>
    <div class="table-scroll">
      <table>
        <thead>
          <tr><th>Level</th><th>Start</th><th>End</th><th>Duration</th><th></th></tr>
        </thead>
        <tbody>
          {#each tingle.intervals as iv}
            <tr>
              <td>{iv.level}</td>
              <td>{fmtTime(iv.started_at)}</td>
              <td>{iv.ended_at ? fmtTime(iv.ended_at) : 'running'}</td>
              <td>{iv.duration_seconds != null ? formatMinutesish(iv.duration_seconds) : '—'}</td>
              <td><button class="link danger" onclick={() => tingle.remove(iv.id)}>delete</button></td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
  </div>
{/if}
```

- [ ] **Step 5: Add the combined-display and merged-control styles**

In the `<style>` block of `frontend/src/routes/timer/+page.svelte`, add these rules (after the existing `.nudge` rule is a natural spot). They style the tingling readout inside the display box and the divider above the tingling controls:

```css
  .tingle-divider {
    height: 1px;
    background: var(--border);
    width: 78%;
    margin: 0.95rem auto 0.8rem;
  }
  .tingle-line {
    display: flex;
    align-items: baseline;
    justify-content: center;
    gap: 0.5rem;
  }
  .tingle-tag {
    font-size: 0.78rem;
    text-transform: uppercase;
    letter-spacing: 0.07em;
    color: var(--tingle);
    font-weight: 700;
  }
  .tingle-clock {
    font-size: 1.5rem;
    font-weight: 650;
    font-variant-numeric: tabular-nums;
  }
  .tingle-lvl {
    font-size: 0.8rem;
    color: var(--text-muted);
  }
  .tingle-controls {
    margin-top: 1rem;
    padding-top: 0.95rem;
    border-top: 1px dashed var(--border);
  }
  .tingle-caption {
    display: inline-flex;
    align-items: center;
    gap: 0.4rem;
    font-size: 0.78rem;
    color: var(--text-muted);
    margin-bottom: 0.5rem;
  }
  .tingle-dot {
    width: 0.6rem;
    height: 0.6rem;
    border-radius: 50%;
    background: var(--tingle);
  }
```

- [ ] **Step 6: Type-check**

Run: `cd frontend && npm run check`
Expected: PASS — no unused-import, type, or Svelte errors. If `check` reports an unused import or symbol, it points to a leftover from the removed tingling card; remove only the flagged leftover.

- [ ] **Step 7: Build**

Run: `cd frontend && npm run build`
Expected: build completes with no errors.

- [ ] **Step 8: Manual verification**

Run: `cd frontend && npm run dev`, open the timer page, and confirm:
- Order top-to-bottom: date bar → combined display → merged controls → 24h timeline bar → posture totals → posture interval table → tingling interval table.
- Start a posture timer: big clock runs; the timeline posture strip grows to the `now` line.
- Start a tingling timer: a smaller `Tingling · {elapsed} · level {n}` line appears below the divider in the *same* display box; a violet block appears on the tingling strip.
- Stop tingling: the readout disappears; no layout jump elsewhere.
- Navigate to a previous day (‹ or the date picker): combined display + controls hide; the timeline bar shows that day's posture + tingling with no `now` line; the tingling interval table shows that day's rows.
- Toggle light/dark (theme control): posture colors, the violet tingling, and the `now` line all read clearly in both themes.

- [ ] **Step 9: Commit**

```bash
git add frontend/src/routes/timer/+page.svelte
git commit -m "feat(timer): combined display, merged controls, 24h timeline, reordered totals"
```

---

## Self-Review

**Spec coverage:**
- Merge two displays into one card → Task 3 Step 3 (combined display block). ✓
- Tingling readout `Tingling · {elapsed} · level {n}` below divider → Task 3 Step 3 + Step 5 styles. ✓
- Merged control panel (dashed divider) → Task 3 Step 3 + `.tingle-controls` style. ✓
- 24h timeline bar, Option A two stacked tracks, axis, `now` marker, empty future, tooltips, legend → Task 1 (geometry) + Task 2 (component). ✓
- Renders for any day; `now` only today → Task 2 (`isToday` gate on `.nowline`) + Task 3 (bar outside `{#if isToday}`). ✓
- Past-day tingling actually loads → Task 3 Steps 1–2 (`loadDay` wired into date nav). ✓
- Totals moved below the bar → Task 3 Step 3 (totals card after the bar). ✓
- Tingling table relocated to bottom, today/any-day when it has rows → Task 3 Step 4. ✓
- Pure helper + unit tests mirroring ratio.ts → Task 1. ✓
- `--tingle` token, dark + light → Task 2 Step 1. ✓
- No backend/API changes → all tasks are under `frontend/`. ✓

**Placeholder scan:** No TBD/TODO; every code step shows complete code; commands include expected output. ✓

**Type consistency:** `postureSegments`/`tinglingSegments`/`nowPct`/`localDayStartMs`/`intervalToSegment` names and signatures are identical across Task 1 (definition), its tests, and Task 2 (consumption). Component props `{ intervals, tingling, date, now }` match the `<TimelineBar ... />` mount in Task 3. Handlers/vars used in Task 3 (`pick`, `stop`, `startTingle`, `stopTingle`, `tingleLevel`, `label`, `nudge`, `postureColorVar`, `formatDuration`, `formatMinutesish`, `sitStandRatio`) all already exist in the current page. ✓
