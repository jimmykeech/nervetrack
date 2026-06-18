# Today timeline — truncation + timer labels

**Date:** 2026-06-18
**Scope:** Two presentation changes to the Today page timeline. Frontend only — no backend, API, or type-shape changes.

## Motivation

1. The timeline renders every logged event in one rail. On busy days this becomes a long scroll. It should show only the most recent events by default, with the option to expand to the full day.
2. Timer intervals can carry a free-text label (e.g. a sitting entry labelled "watching tv on couch"), stored in `Interval.label`. Today this label is dropped — the timeline shows the posture and duration but not the label. Notes attached to timer entries should be visible, the same way pain-jab context and standalone notes already are.

## Change 1 — Show timer labels

**`frontend/src/lib/timeline.ts`**
- Add `label: string | null` to the `timer` variant of `TimelineEvent`.
- Populate it from `iv.label` in `buildTimeline`.

**`frontend/src/lib/components/Timeline.svelte`**
- In the `timer` branch, when `ev.label` is a non-empty string (after trim), render it as a `.rail-sub` line below the existing duration line — matching how pain `context` and note `body` already render.
- Empty/null labels render nothing extra (current behaviour preserved).

## Change 2 — Truncate to last 10, expand/collapse

**`frontend/src/lib/components/Timeline.svelte`**
- `events` (from `buildTimeline`) is already newest-first.
- Add component-local state `let expanded = $state(false)`.
- Derive `const visibleEvents = $derived(expanded ? events : events.slice(0, 10))`.
- Render `visibleEvents` instead of `events` in the rail.
- When `events.length > 10`, render a toggle button below the rail:
  - collapsed: label `Show all (N)`, where `N = events.length`
  - expanded: label `Show less`
  - clicking flips `expanded`.
- When `events.length <= 10`, no toggle is shown.
- Truncation is presentation-only. Note edit/remove continues to operate on whatever is currently visible; collapsing does not affect persisted data.

## Testing

- **`frontend/src/lib/timeline.test.ts`**: extend the existing suite to assert the `timer` event carries the interval's `label` (both a non-null value and the null case).
- There is no component-test harness in this project (only `*.test.ts` unit tests on `lib/` pure functions). The truncation is a one-line `.slice(0, 10)` plus a boolean toggle in the component; it will be verified manually by running the app. No new test infrastructure is introduced for this change.

## Out of scope

- Pagination / "load 10 more at a time" (rejected in favour of a single show-all/show-less toggle).
- Persisting the expanded state across reloads.
- Any change to how labels are entered or stored.
