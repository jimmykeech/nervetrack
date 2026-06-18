# Today Timeline Truncation + Timer Labels Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show timer-interval labels in the Today timeline and truncate the timeline to the 10 most recent events with a show-all/show-less toggle.

**Architecture:** Pure-function change in `timeline.ts` (add `label` to the timer event) plus presentation changes in `Timeline.svelte` (render the label, slice to 10, add a toggle). No backend, API, or type-shape changes.

**Tech Stack:** SvelteKit (Svelte 5 runes), TypeScript, Vitest.

---

### Task 1: Carry timer label through buildTimeline

**Files:**
- Modify: `frontend/src/lib/timeline.ts`
- Test: `frontend/src/lib/timeline.test.ts`

- [ ] **Step 1: Write the failing test**

Add this test inside the `describe('buildTimeline', ...)` block in `frontend/src/lib/timeline.test.ts`:

```ts
it('carries the timer interval label onto the timer event', () => {
  const events = buildTimeline(
    entry({
      timer_intervals: [
        {
          id: 'i1',
          entry_date: '2026-06-13',
          posture: 'sitting',
          started_at: '2026-06-13T09:02:00',
          ended_at: '2026-06-13T10:20:00',
          duration_seconds: 4680,
          label: 'watching tv on couch'
        },
        {
          id: 'i2',
          entry_date: '2026-06-13',
          posture: 'standing',
          started_at: '2026-06-13T11:00:00',
          ended_at: null,
          duration_seconds: null,
          label: null
        }
      ]
    })
  );
  expect(events).toMatchObject([
    { kind: 'timer', label: null },
    { kind: 'timer', label: 'watching tv on couch' }
  ]);
});
```

(Note: events are newest-first, so the 11:00 null-label interval comes before the 09:02 labelled one.)

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/lib/timeline.test.ts`
Expected: FAIL — the timer events have no `label` property, so the `toMatchObject` with `label: 'watching tv on couch'` does not match.

- [ ] **Step 3: Add `label` to the timer event type and populate it**

In `frontend/src/lib/timeline.ts`, change the `timer` member of the `TimelineEvent` union to include `label`:

```ts
export type TimelineEvent =
  | {
      kind: 'timer';
      at: string;
      posture: Posture;
      durationSeconds: number | null;
      running: boolean;
      label: string | null;
    }
  | { kind: 'pain'; at: string; level: number | null; context: string | null }
  | { kind: 'check'; at: string; label: string }
  | { kind: 'note'; at: string; id: string; body: string };
```

Then in `buildTimeline`, update the timer push to include the label:

```ts
  for (const iv of entry.timer_intervals) {
    events.push({
      kind: 'timer',
      at: iv.started_at,
      posture: iv.posture,
      durationSeconds: iv.duration_seconds,
      running: iv.ended_at == null,
      label: iv.label
    });
  }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npx vitest run src/lib/timeline.test.ts`
Expected: PASS — all tests in the file pass, including the new one.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/timeline.ts frontend/src/lib/timeline.test.ts
git commit -m "feat(timeline): carry timer interval label onto timeline event"
```

---

### Task 2: Render the timer label in the Timeline component

**Files:**
- Modify: `frontend/src/lib/components/Timeline.svelte`

- [ ] **Step 1: Render the label as a sub-line in the timer branch**

In `frontend/src/lib/components/Timeline.svelte`, the timer branch currently reads:

```svelte
            {#if ev.kind === 'timer'}
              <div class="rail-top">
                <span>{POSTURE_ICON[ev.posture]} {POSTURE_LABEL[ev.posture]}</span>
                <span class="rail-time">{fmtTime(ev.at)}</span>
              </div>
              <div class="rail-sub">
                {ev.running ? 'ongoing' : formatMinutesish(ev.durationSeconds ?? 0)}
              </div>
```

Add a label sub-line after the duration sub-line, shown only when the label is non-empty:

```svelte
            {#if ev.kind === 'timer'}
              <div class="rail-top">
                <span>{POSTURE_ICON[ev.posture]} {POSTURE_LABEL[ev.posture]}</span>
                <span class="rail-time">{fmtTime(ev.at)}</span>
              </div>
              <div class="rail-sub">
                {ev.running ? 'ongoing' : formatMinutesish(ev.durationSeconds ?? 0)}
              </div>
              {#if ev.label?.trim()}<div class="rail-sub">{ev.label}</div>{/if}
```

- [ ] **Step 2: Verify it type-checks**

Run: `cd frontend && npm run check`
Expected: No new errors referencing `Timeline.svelte` (`ev.label` is a known property of the timer event after Task 1).

- [ ] **Step 3: Commit**

```bash
git add frontend/src/lib/components/Timeline.svelte
git commit -m "feat(timeline): show timer interval label in timeline"
```

---

### Task 3: Truncate to 10 events with show-all / show-less toggle

**Files:**
- Modify: `frontend/src/lib/components/Timeline.svelte`

- [ ] **Step 1: Add expanded state and visibleEvents derivation**

In the `<script>` block of `frontend/src/lib/components/Timeline.svelte`, just after the existing `const events = $derived(buildTimeline(entry));` line, add:

```ts
  let expanded = $state(false);
  const visibleEvents = $derived(expanded ? events : events.slice(0, 10));
```

- [ ] **Step 2: Render visibleEvents and add the toggle**

Change the `{#each events as ev}` loop to iterate `visibleEvents`:

```svelte
      {#each visibleEvents as ev}
```

Then, immediately after the closing `</div>` of the `.rail` div (i.e. after the `{/each}` and its wrapping `</div>`, still inside the `{:else}` branch), add the toggle button:

```svelte
    {#if events.length > 10}
      <button class="link show-toggle" onclick={() => (expanded = !expanded)}>
        {expanded ? 'Show less' : `Show all (${events.length})`}
      </button>
    {/if}
```

For reference, the resulting `{:else}` block structure is:

```svelte
  {:else}
    <div class="rail">
      {#each visibleEvents as ev}
        ...
      {/each}
    </div>
    {#if events.length > 10}
      <button class="link show-toggle" onclick={() => (expanded = !expanded)}>
        {expanded ? 'Show less' : `Show all (${events.length})`}
      </button>
    {/if}
  {/if}
```

- [ ] **Step 3: Add toggle styling**

In the `<style>` block, add a `.show-toggle` rule (the `.link` class already exists). Place it after the existing `.link` rule:

```css
  .show-toggle {
    display: block;
    margin: 0.6rem auto 0;
  }
```

- [ ] **Step 4: Verify it type-checks**

Run: `cd frontend && npm run check`
Expected: No new errors referencing `Timeline.svelte`.

- [ ] **Step 5: Manual verification**

Run: `cd frontend && npm run dev`
Then in the browser on the Today page:
- With ≤10 events: no toggle appears, all events show.
- With >10 events: only the 10 newest show, and a `Show all (N)` button appears below the rail. Clicking it reveals all events and the button becomes `Show less`; clicking again collapses back to 10.
- A timer entry with a label (e.g. a sitting entry labelled "watching tv on couch") shows that label text under its duration line.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/lib/components/Timeline.svelte
git commit -m "feat(timeline): truncate to 10 most recent events with show-all toggle"
```

---

### Task 4: Full verification

- [ ] **Step 1: Run the full frontend test + lint suite**

Run: `cd frontend && npx vitest run && npm run lint`
Expected: All tests pass; prettier and eslint report no errors. If prettier flags formatting on changed files, run `npm run format` and amend the relevant commit.

- [ ] **Step 2: Confirm clean tree**

Run: `git status`
Expected: working tree clean (all changes committed).
