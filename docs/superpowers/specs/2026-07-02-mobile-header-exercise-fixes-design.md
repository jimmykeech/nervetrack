# Mobile fixes — header + exercise date/intensity

**Date:** 2026-07-02
**Status:** Draft — awaiting review

## Problem

Two mobile layout issues:

1. **Header** (`frontend/src/routes/+layout.svelte`). The `.topline` places the
   brand on the left and a cluster of `ThemeToggle` + the full user email +
   a "Sign out" button on the right, all on one row. At phone widths the email
   text eats the available space and the whole cluster crowds together.
2. **Exercise page** (`frontend/src/routes/exercises/+page.svelte`). The
   "Session date" and "Intensity (1–10)" fields sit in a flex `.row`
   (`.field` = `flex: 1 1 8rem`). At ~375px they are just narrow enough not to
   wrap, so they cram side-by-side and the date input is squashed.

## Goal

Fix both at the existing `640px` breakpoint. No behavioural changes. Desktop
layout unchanged in both cases.

## Design

### 1. Header — relocate account actions on mobile

At ≤640px, show only **brand (left) + theme toggle (right)** in the header;
hide the email display and the "Sign out" button. Nothing is lost: the Settings
page already has an **Account** section (`frontend/src/routes/settings/+page.svelte`
~line 85) that shows "Signed in as `<email>`" and a "Sign out" button, and it
imports `ThemeToggle` too.

Implementation: in the `+layout.svelte` scoped `<style>`, add

```css
@media (max-width: 640px) {
  .account .muted,
  .account .logout {
    display: none;
  }
}
```

- `.account .muted` is the email `<span class="muted small">`.
- `.account .logout` is the "Sign out" button.
- `ThemeToggle` (rendered as `.theme` inside `.account`) stays visible.

Desktop (>640px) is unchanged.

### 2. Exercise page — stack date/intensity on mobile

The date/intensity row currently uses inline styles:

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

Refactor the widths out of inline styles into scoped classes so the mobile
override is clean (no `!important` fighting inline styles), and add a scoped
`<style>` block to the page (it currently has none for this row):

- Add class `session-meta` to the row and `f-intensity` to the intensity field;
  keep `margin: 0` behaviour via the scoped rules.
- Desktop: date field flexes, intensity field capped at `10rem` (as today).
- At ≤640px: `.session-meta` becomes `flex-direction: column; align-items: stretch;`
  and `.session-meta .field` gets `max-width: none;` so both fields are full
  width and stack vertically.

Concrete markup and CSS (exact strings finalised in the implementation plan):

```svelte
<div class="card">
  <div class="row session-meta">
    <div class="field f-date">
      <label>Session date</label>
      <input type="date" bind:value={date} />
    </div>
    <div class="field f-intensity">
      <label>Intensity (1–10)</label>
      <input type="number" min="1" max="10" step="0.5" bind:value={intensity} />
    </div>
  </div>
</div>

<style>
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
</style>
```

## Non-goals (YAGNI)

- No hamburger/dropdown menu, no avatar menu, no nav restructuring.
- No new Settings content (Account section already covers email + sign out).
- No changes to desktop layout.
- No changes to the theme toggle behaviour.

## Verification

- `npm run test` — existing tests pass (no logic touched).
- `npm run check` — no type errors.
- `npm run lint` — passes.
- Manual at ~375px: header shows only brand + theme toggle, uncrowded; the
  email + Sign out are gone from the header but present on Settings; the
  exercise Session date and Intensity stack vertically and read cleanly.
  Confirm desktop (>640px) is visually unchanged for both.
