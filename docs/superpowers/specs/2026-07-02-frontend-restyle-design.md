# Frontend restyle — "Clear Sky" (modern minimal mono)

**Date:** 2026-07-02
**Status:** Draft — awaiting review

## Problem

Two issues with the current frontend:

1. **Colour scheme.** The "Still Water" palette (warm earthy browns, gold
   `#cfa56a` accent, Fraunces serif headings) is disliked. A cleaner, more
   modern look is wanted.
2. **Mobile formatting.** Several pages have multi-column grids and tables
   that never collapse on small screens, causing cramped layouts and
   horizontal overflow.

## Goal

Reskin the app to a **modern minimal mono** look — cool-slate neutrals with a
single sky-blue accent, Space Grotesk headings — across both dark and light
themes (dark stays default, theme toggle preserved). Fix the mobile layout
breakages. No functional/behavioural changes.

## Design approach

The app is fully token-driven: `frontend/src/app.css` defines CSS custom
properties consumed everywhere. The restyle keeps all token **names**
unchanged and swaps their **values**, so components inherit the new look
without edits. Work falls into four buckets: palette tokens, typography,
one new button utility, and mobile layout fixes.

### 1. Palette tokens (`frontend/src/app.css`)

Replace the colour values in `:root` (dark, default) and `[data-theme='light']`.
All other tokens (radii, `--maxw`, `--shadow` structure, `*-soft` mixes,
posture mappings) keep their existing definitions; only the base colour
values below change.

**Dark (`:root`):**
```
--bg: #0e1116;
--surface: #151a21;
--surface-2: #1c222b;
--border: #273039;
--text: #e4e9ef;
--text-muted: #94a0ac;
--text-faint: #626d7a;
--accent: #38a9f0;
--good: #3fb883;
--caution: #d9a441;
--bad: #e5645f;
--rest: #7c8aa8;
--move: #4bb0d6;
--shadow: 0 2px 10px rgba(0, 0, 0, 0.35);
```

**Light (`[data-theme='light']`):**
```
--bg: #f4f6f9;
--surface: #ffffff;
--surface-2: #eef1f6;
--border: #dde3ea;
--text: #1b2430;
--text-muted: #5c6875;
--text-faint: #8a97a5;
--accent: #1f8fd6;
--good: #2f9e6b;
--caution: #c08a2e;
--bad: #cf4d47;
--rest: #5b6fa0;
--move: #2b93bd;
--shadow: 0 2px 12px rgba(20, 40, 60, 0.08);
```

The `*-soft`, posture, and `--accent-soft` tokens are derived via
`color-mix` from the above and need no change. The `.status-G/.status-A/
.status-R` ink (text) colours are retuned for contrast on the new fills:
`.status-G` text `#062015`, `.status-A` text `#241900`, `.status-R` text
`#2a0b09` (dark, legible ink on the green/amber/red fills; adjust only if a
contrast check fails).

### 2. Theme-colour meta (`frontend/src/app.html`)

Update `<meta name="theme-color" content="#1b2330" />` to
`content="#0e1116"` so the mobile browser chrome matches the new dark bg.

### 3. Typography

- Display/heading font → **Space Grotesk**.
  - Add dependency `@fontsource-variable/space-grotesk`.
  - In `frontend/src/routes/+layout.svelte`, replace
    `import '@fontsource-variable/fraunces';` with
    `import '@fontsource-variable/space-grotesk';`.
  - In `app.css`, set
    `--font-display: 'Space Grotesk Variable', system-ui, sans-serif;`.
  - Remove `@fontsource-variable/fraunces` from `package.json` dependencies
    (no longer imported).
- Body font → **unchanged** (Hanken Grotesk Variable via `--font-ui`).

### 4. Primary-button utility (`frontend/src/app.css`)

Add a `.btn-primary` class (filled sky-blue accent) alongside the existing
base `button` styles:

```css
.btn-primary {
  background: var(--accent);
  border-color: var(--accent);
  color: #04121b;
  font-weight: 600;
}
.btn-primary:hover {
  background: color-mix(in srgb, var(--accent) 88%, #000);
  border-color: color-mix(in srgb, var(--accent) 88%, #000);
}
```

Apply `class="btn-primary"` to the single clearest primary CTA on each of
these pages, leaving all other buttons neutral:
- `frontend/src/routes/timer/+page.svelte` — the start/primary timer action.
- `frontend/src/routes/chat/+page.svelte` — the **Send** submit button.
- `frontend/src/routes/login/+page.svelte` — the sign-in button.

(The implementation plan will confirm exact button selectors on each page;
the rule is one primary CTA per listed page, base buttons otherwise.)

### 5. Mobile layout fixes

Add responsive collapse at a `640px` breakpoint (matching the breakpoint
Chat and Records already use). Each fix is scoped to its file:

- **`app.css` `.grid-2`** — currently always `1fr 1fr`. Add
  `@media (max-width: 640px) { .grid-2 { grid-template-columns: 1fr; } }`.
  Fixes the Today page.
- **`frontend/src/routes/timer/+page.svelte`** — the `repeat(4, 1fr)` grid
  → 2 columns at ≤640px; the `repeat(2, 1fr)` grid → 1 column at ≤640px.
- **`frontend/src/routes/weekly/+page.svelte`** — the `repeat(3, 1fr)` grid
  → 1 column at ≤640px.
- **Tables** in `frontend/src/routes/timer/+page.svelte` and
  `frontend/src/routes/history/+page.svelte` — wrap each `<table>` in a
  `<div class="table-scroll">` and add a global helper in `app.css`:
  `.table-scroll { overflow-x: auto; -webkit-overflow-scrolling: touch; }`
  so wide tables scroll within their card instead of overflowing the page.
- **`frontend/src/routes/+page.svelte`** (Today) — the inline flex children
  with `min-width: 8rem` / `min-width: 10rem` can overflow narrow screens;
  ensure their container wraps (`flex-wrap: wrap`) and/or reduce the
  min-widths so the row reflows cleanly at ~360px.

Chat and Records already collapse correctly and are not touched for layout.

## Non-goals (YAGNI)

- No component restructuring, no new pages, no navigation redesign.
- No change to the theme toggle behaviour or persistence.
- No chart re-theming beyond what the token swap provides (Chart.js reads
  CSS variables where already wired; no new chart work).
- No change to body typography.
- No blanket conversion of every button to primary — one CTA per listed page
  only.

## Verification

- `npm run test` (frontend) — all existing tests pass (token/font changes
  don't touch logic; theme tests are pure-string).
- `npm run check` — no type errors.
- `npm run lint` — passes.
- Manual: load every page (Today, Timer, History, Exercises, Records,
  Weekly, Chat, Settings, Login) at ~375px width and at desktop, in both
  dark and light themes. Confirm: no horizontal overflow; grids collapse;
  tables scroll within their cards; headings render in Space Grotesk;
  accent/links/focus rings are sky-blue; status pills remain legible.
