# Mobile Header + Exercise Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix two mobile layout issues — the cramped header account cluster, and the squashed exercise date/intensity row — at the 640px breakpoint, with no behavioural or desktop changes.

**Architecture:** Pure CSS/markup. Task 1 adds a media query to the layout header hiding the email + Sign out on mobile (both already available on Settings). Task 2 moves the exercise date/intensity inline width styles into scoped classes and stacks the fields vertically on mobile.

**Tech Stack:** SvelteKit (Svelte 5), scoped component CSS, Vitest.

## Global Constraints

- Frontend lives in `frontend/`; run all `npm` commands from that directory.
- Breakpoint is `640px` (matches the rest of the app).
- No behavioural changes; desktop (>640px) layout unchanged in both tasks.
- These are presentational changes with no logic. Do NOT add unit tests (an assert-nothing test is a defect). Verify each task with `npm run check`, `npm run lint`, and `npm run test` all staying green, plus the manual check described.

---

### Task 1: Header — hide email + Sign out on mobile

**Files:**
- Modify: `frontend/src/routes/+layout.svelte` (scoped `<style>`)

**Interfaces:**
- Consumes: nothing.
- Produces: nothing (leaf UI change).

- [ ] **Step 1: Add the mobile media query**

In `frontend/src/routes/+layout.svelte`, inside the scoped `<style>` block, immediately before the closing `</style>`, add:

```css
  @media (max-width: 640px) {
    .account .muted,
    .account .logout {
      display: none;
    }
  }
```

This hides the email `<span class="muted small">` and the `<button class="logout">Sign out</button>` at ≤640px. `ThemeToggle` (`.theme`) and the brand remain. Desktop is unaffected.

- [ ] **Step 2: Verify the suite stays green**

Run from `frontend/`:

```bash
npm run check && npm run lint && npm run test
```

Expected: all exit 0 (no logic touched; 41 tests pass).

- [ ] **Step 3: Manual visual check**

With `npm run dev` running, at ~375px width: the header shows only the brand (left) and the theme-toggle (right), no crowding; the email and Sign out are gone from the header. Confirm they still appear on the Settings → Account section. At desktop width (>640px), the header still shows email + Sign out as before.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/routes/+layout.svelte
git commit -m "fix(mobile): hide header email + sign-out on small screens"
```

---

### Task 2: Exercise page — stack date/intensity on mobile

**Files:**
- Modify: `frontend/src/routes/exercises/+page.svelte` (date/intensity markup + scoped `<style>`)

**Interfaces:**
- Consumes: nothing.
- Produces: nothing (leaf UI change).

- [ ] **Step 1: Replace the date/intensity row markup**

In `frontend/src/routes/exercises/+page.svelte`, replace this block:

```svelte
  <div class="row" style="align-items: center; gap: 1rem">
    <div class="field" style="margin: 0">
      <label>Session date</label>
      <input type="date" bind:value={date} />
    </div>
    <div class="field" style="margin: 0; max-width: 10rem">
      <label>Intensity (1–10)</label>
      <input type="number" min="1" max="10" step="0.5" bind:value={intensity} />
    </div>
  </div>
```

with (inline width styles removed; scoped classes added):

```svelte
  <div class="row session-meta">
    <div class="field">
      <label>Session date</label>
      <input type="date" bind:value={date} />
    </div>
    <div class="field f-intensity">
      <label>Intensity (1–10)</label>
      <input type="number" min="1" max="10" step="0.5" bind:value={intensity} />
    </div>
  </div>
```

- [ ] **Step 2: Add the scoped styles**

In the same file, inside the existing `<style>` block, immediately before the closing `</style>`, add:

```css
  .session-meta {
    align-items: center;
    gap: 1rem;
  }
  .session-meta .field {
    margin: 0;
  }
  .f-intensity {
    max-width: 10rem;
  }
  @media (max-width: 640px) {
    .session-meta {
      flex-direction: column;
      align-items: stretch;
    }
    .session-meta .field {
      max-width: none;
    }
  }
```

This reproduces the old desktop layout (fields side-by-side, `margin: 0`, intensity capped at `10rem`) via classes instead of inline styles, and at ≤640px stacks the fields vertically at full width. (`.session-meta .field` has higher specificity than `.f-intensity`, so `max-width: none` wins on mobile.)

- [ ] **Step 3: Verify the suite stays green**

Run from `frontend/`:

```bash
npm run check && npm run lint && npm run test
```

Expected: all exit 0.

- [ ] **Step 4: Manual visual check**

With `npm run dev` running: at ~375px the Session date and Intensity fields stack vertically, each full width, no squashing. At desktop width they sit side-by-side with the intensity field narrow (≤10rem), matching the previous layout.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/routes/exercises/+page.svelte
git commit -m "fix(mobile): stack exercise session date/intensity fields"
```

---

## Self-Review

**Spec coverage:**
- Header: hide email + Sign out ≤640px, keep brand + toggle (spec §1) → Task 1. Verified class names against markup: `.account` wraps `<span class="muted small">` (email) and `<button class="logout">` (Sign out); `ThemeToggle` renders `.theme`.
- Exercise: move inline widths to scoped classes, stack ≤640px (spec §2) → Task 2. The exercises page already has a `<style>` block, so the rules are appended to it (not a new block).
- Verification (spec) → each task's check/lint/test + manual steps.
- Non-goals respected: no menu/dropdown, no new Settings content, no desktop changes, no toggle-behaviour change.

**Placeholder scan:** No TBD/TODO. All edits give exact old→new strings or exact CSS to append.

**Type consistency:** No types/functions. Class names consistent: `.session-meta` and `.f-intensity` defined in Task 2 step 2 match their use in Task 2 step 1; `.account .muted` / `.account .logout` in Task 1 match the existing markup.
