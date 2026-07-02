# Frontend Restyle ("Clear Sky") Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reskin the frontend to a modern-minimal-mono look (cool-slate neutrals + sky-blue accent, Space Grotesk headings) across both themes, and fix mobile layout breakages — with no behavioural changes.

**Architecture:** The app is token-driven via CSS custom properties in `frontend/src/app.css`. The restyle swaps token *values* (names unchanged, so components inherit the look), swaps the display font, adds one `.btn-primary` utility applied to a few primary CTAs, and adds responsive collapses at a 640px breakpoint.

**Tech Stack:** SvelteKit (Svelte 5), TypeScript, plain CSS custom properties, `@fontsource-variable/*` fonts, Vitest.

## Global Constraints

- Frontend lives in `frontend/`; run all `npm` commands from that directory.
- Keep all existing CSS token **names**; only change values / add new utilities.
- Dark theme stays the default (`:root`); light is `[data-theme='light']`. Theme toggle behaviour is unchanged.
- Responsive breakpoint is `640px` (matches the breakpoint Chat and Records already use), except the timer totals grid which may use `480px` as noted.
- No behavioural/functional changes, no component restructuring, no new pages.
- These are presentational changes with no logic. Do **not** add new unit tests (a CSS value has no behaviour to assert; an assert-nothing test is a defect). Verify each task with `npm run check`, `npm run lint`, and `npm run test` all staying green, plus the manual visual check described in the task.

---

### Task 1: Palette token swap + theme-colour meta

**Files:**
- Modify: `frontend/src/app.css` (`:root` colours ~7-22, `[data-theme='light']` colours ~47-62, `.status-*` ink ~202-216)
- Modify: `frontend/src/app.html` (theme-color meta)

**Interfaces:**
- Consumes: nothing.
- Produces: the new colour token values every component reads. Token names unchanged.

- [ ] **Step 1: Swap the dark (`:root`) colour values**

In `frontend/src/app.css`, replace this block:

```css
  --bg: #1a1713;
  --surface: #221d16;
  --surface-2: #2a241b;
  --border: #342c20;
  --text: #ece2d3;
  --text-muted: #9b9482;
  --text-faint: #6f6a5c;
  --accent: #cfa56a;

  --good: #85ad7f;
  --caution: #cdb06a;
  --bad: #d7705f;
  --rest: #7e90b2;
  --move: #cda35e;

  --shadow: 0 2px 10px rgba(0, 0, 0, 0.25);
```

with:

```css
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

- [ ] **Step 2: Swap the light-theme colour values**

Replace this block (inside `[data-theme='light']`):

```css
  --bg: #f1ebdf;
  --surface: #faf5ec;
  --surface-2: #ece4d4;
  --border: #e0d7c5;
  --text: #38423a;
  --text-muted: #8c9486;
  --text-faint: #a9af9f;
  --accent: #bd8a55;

  --good: #5f8a5f;
  --caution: #c79a4a;
  --bad: #b0524a;
  --rest: #6e80a0;
  --move: #b9863f;

  --shadow: 0 2px 10px rgba(74, 58, 30, 0.08);
```

with:

```css
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

(The `*-soft`, `--accent-soft`, and posture tokens are derived from these via `color-mix`/`var()` and need no edit.)

- [ ] **Step 3: Retune the status-pill ink colours for the new fills**

Replace the three `color:` lines in the `.status-*` rules:

```css
.status-G {
  background: var(--good);
  color: #11240f;
  border-color: var(--good);
}
.status-A {
  background: var(--caution);
  color: #2c1f00;
  border-color: var(--caution);
}
.status-R {
  background: var(--bad);
  color: #2a0c08;
  border-color: var(--bad);
}
```

with (only the `color:` values change):

```css
.status-G {
  background: var(--good);
  color: #062015;
  border-color: var(--good);
}
.status-A {
  background: var(--caution);
  color: #241900;
  border-color: var(--caution);
}
.status-R {
  background: var(--bad);
  color: #2a0b09;
  border-color: var(--bad);
}
```

- [ ] **Step 4: Update the mobile theme-colour meta**

In `frontend/src/app.html`, replace:

```html
    <meta name="theme-color" content="#1b2330" />
```

with:

```html
    <meta name="theme-color" content="#0e1116" />
```

- [ ] **Step 5: Verify the suite stays green**

Run from `frontend/`:

```bash
npm run check && npm run lint && npm run test
```

Expected: all exit 0 (check 0 errors, lint clean, tests all pass — token changes touch no logic).

- [ ] **Step 6: Manual visual check**

Run `npm run dev` from `frontend/` and load the app. Confirm: background is dark slate `#0e1116`, links/focus rings/active nav are sky-blue, cards read cleanly. Toggle to light theme and confirm the light palette (near-white surfaces, deeper sky-blue accent). No manual test file to write.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/app.css frontend/src/app.html
git commit -m "style: swap palette to Clear Sky (sky-blue on cool slate), both themes"
```

---

### Task 2: Typography — Space Grotesk headings

**Files:**
- Modify: `frontend/package.json` + `frontend/package-lock.json` (deps)
- Modify: `frontend/src/routes/+layout.svelte` (font import)
- Modify: `frontend/src/app.css` (`--font-display`)

**Interfaces:**
- Consumes: nothing.
- Produces: `--font-display` now resolves to Space Grotesk; heading font family available app-wide (headings already use `var(--font-display)`).

- [ ] **Step 1: Add Space Grotesk, remove Fraunces**

Run from `frontend/`:

```bash
npm install @fontsource-variable/space-grotesk
npm uninstall @fontsource-variable/fraunces
```

Expected: `@fontsource-variable/space-grotesk` appears in `dependencies`; `@fontsource-variable/fraunces` is removed; both commands exit 0.

- [ ] **Step 2: Swap the font import**

In `frontend/src/routes/+layout.svelte`, replace:

```ts
  import '@fontsource-variable/fraunces';
```

with:

```ts
  import '@fontsource-variable/space-grotesk';
```

- [ ] **Step 3: Point `--font-display` at Space Grotesk**

In `frontend/src/app.css`, replace:

```css
  --font-display: 'Fraunces Variable', Georgia, 'Times New Roman', serif;
```

with:

```css
  --font-display: 'Space Grotesk Variable', system-ui, -apple-system, sans-serif;
```

- [ ] **Step 4: Verify the suite stays green**

Run from `frontend/`:

```bash
npm run check && npm run lint && npm run test
```

Expected: all exit 0. (No stray remaining import of `fraunces` — grep to confirm: `grep -rn fraunces frontend/src` returns nothing.)

- [ ] **Step 5: Manual visual check**

With `npm run dev` running, confirm headings (page titles, card `h2`/`h3`, the brand wordmark) now render in Space Grotesk (geometric sans), while body text remains Hanken Grotesk. No serif remains.

- [ ] **Step 6: Commit**

```bash
git add frontend/package.json frontend/package-lock.json frontend/src/routes/+layout.svelte frontend/src/app.css
git commit -m "style: switch display font to Space Grotesk"
```

---

### Task 3: `.btn-primary` utility + apply to primary CTAs

**Files:**
- Modify: `frontend/src/app.css` (add `.btn-primary`)
- Modify: `frontend/src/routes/chat/+page.svelte` (Send button)
- Modify: `frontend/src/routes/login/+page.svelte` (submit button)
- Modify: `frontend/src/routes/settings/+page.svelte` ("Save AI settings" button)

**Interfaces:**
- Consumes: `--accent` (Task 1).
- Produces: a `.btn-primary` class usable on any `<button>`.

Note: the timer page has no single neutral primary button (starting = tapping semantic-coloured posture tiles), so it does not receive `.btn-primary`. Settings "Save AI settings" — a currently-neutral primary action — is used as the third target instead. Save/confirm buttons that already use `.status-G` (green) keep their existing treatment.

- [ ] **Step 1: Add the `.btn-primary` rule**

In `frontend/src/app.css`, immediately after the `button:disabled { ... }` rule (before the `:focus-visible` rule), add:

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

- [ ] **Step 2: Apply to the Chat Send button**

In `frontend/src/routes/chat/+page.svelte`, replace:

```svelte
      <button type="submit" disabled={chat.sending || !draft.trim()}>Send</button>
```

with:

```svelte
      <button type="submit" class="btn-primary" disabled={chat.sending || !draft.trim()}>Send</button>
```

- [ ] **Step 3: Apply to the Login submit button**

In `frontend/src/routes/login/+page.svelte`, replace:

```svelte
        <button type="submit" disabled={busy}>{registering ? 'Create account' : 'Sign in'}</button>
```

with:

```svelte
        <button type="submit" class="btn-primary" disabled={busy}>{registering ? 'Create account' : 'Sign in'}</button>
```

- [ ] **Step 4: Apply to the Settings "Save AI settings" button**

In `frontend/src/routes/settings/+page.svelte`, replace:

```svelte
    <button onclick={saveLlm} disabled={llmBusy || !model.trim()}>Save AI settings</button>
```

with:

```svelte
    <button onclick={saveLlm} class="btn-primary" disabled={llmBusy || !model.trim()}>Save AI settings</button>
```

- [ ] **Step 5: Verify the suite stays green**

Run from `frontend/`:

```bash
npm run check && npm run lint && npm run test
```

Expected: all exit 0.

- [ ] **Step 6: Manual visual check**

With `npm run dev` running: the Chat **Send** button, Login **Sign in / Create account** button, and Settings **Save AI settings** button render as filled sky-blue; other buttons stay neutral; green `.status-G` save buttons (Weekly/Exercises/Today) are unchanged.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/app.css frontend/src/routes/chat/+page.svelte frontend/src/routes/login/+page.svelte frontend/src/routes/settings/+page.svelte
git commit -m "style: add btn-primary and apply to key CTAs (send, login, save AI)"
```

---

### Task 4: Mobile responsive fixes

**Files:**
- Modify: `frontend/src/app.css` (`.grid-2` collapse + `.table-scroll` helper)
- Modify: `frontend/src/routes/timer/+page.svelte` (grids collapse + table wrap)
- Modify: `frontend/src/routes/weekly/+page.svelte` (metrics grid collapse)
- Modify: `frontend/src/routes/history/+page.svelte` (table wrap)

**Interfaces:**
- Consumes: nothing.
- Produces: `.table-scroll` helper class (horizontal scroll container).

- [ ] **Step 1: Collapse `.grid-2` and add the `.table-scroll` helper**

In `frontend/src/app.css`, find the `.grid-2` rule:

```css
.grid-2 {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0.75rem;
}
```

and immediately after it add:

```css
@media (max-width: 640px) {
  .grid-2 {
    grid-template-columns: 1fr;
  }
}

.table-scroll {
  overflow-x: auto;
  -webkit-overflow-scrolling: touch;
}
```

- [ ] **Step 2: Collapse the timer grids on mobile**

In `frontend/src/routes/timer/+page.svelte`, at the **end** of the existing `<style>` block (before `</style>`), add:

```css
  @media (max-width: 640px) {
    .postures {
      grid-template-columns: 1fr;
    }
    .tgrid {
      grid-template-columns: repeat(2, 1fr);
    }
  }
```

- [ ] **Step 3: Wrap the timer intervals table for horizontal scroll**

In `frontend/src/routes/timer/+page.svelte`, wrap the `<table>…</table>` element (the intervals table, currently starting `<table>` and ending `</table>`) in a scroll container. Replace the opening `<table>` with:

```svelte
          <div class="table-scroll">
            <table>
```

and the matching closing `</table>` with:

```svelte
            </table>
          </div>
```

(Preserve the table's inner markup exactly; only add the wrapping `<div class="table-scroll">` around it. Match the existing indentation of the surrounding block.)

- [ ] **Step 4: Collapse the weekly metrics grid on mobile**

In `frontend/src/routes/weekly/+page.svelte`, at the **end** of the existing `<style>` block (before `</style>`), add:

```css
  @media (max-width: 640px) {
    .metrics {
      grid-template-columns: 1fr;
    }
  }
```

- [ ] **Step 5: Wrap the history table for horizontal scroll**

In `frontend/src/routes/history/+page.svelte`, wrap the `<table>…</table>` element in a scroll container. Replace the opening `<table>` with:

```svelte
  <div class="table-scroll">
    <table>
```

and the matching closing `</table>` with:

```svelte
    </table>
  </div>
```

(Preserve the table's inner markup exactly; match the existing indentation.)

- [ ] **Step 6: Verify the suite stays green**

Run from `frontend/`:

```bash
npm run check && npm run lint && npm run test
```

Expected: all exit 0.

- [ ] **Step 7: Manual mobile check**

With `npm run dev` running, open the browser devtools responsive mode at ~375px width and visit every page (Today, Timer, History, Exercises, Records, Weekly, Chat, Settings, Login) in both themes. Confirm:
- No horizontal page overflow anywhere.
- Today's `.grid-2` stacks to one column.
- Timer: posture buttons stack one per row; totals show as a 2×2 grid; the intervals table scrolls horizontally inside its card rather than stretching the page.
- Weekly metrics stack to one column.
- History table scrolls horizontally inside its card.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/app.css frontend/src/routes/timer/+page.svelte frontend/src/routes/weekly/+page.svelte frontend/src/routes/history/+page.svelte
git commit -m "fix(mobile): collapse grids and make wide tables scroll on small screens"
```

---

## Self-Review

**Spec coverage:**
- Palette tokens dark + light (spec §1) → Task 1 steps 1-2.
- Status-pill ink retune (spec §1) → Task 1 step 3.
- theme-color meta (spec §2) → Task 1 step 4.
- Space Grotesk display font, keep body, remove Fraunces (spec §3) → Task 2.
- `.btn-primary` utility + apply to primary CTAs (spec §4) → Task 3. Deviation: timer has no neutral single primary button, so Settings "Save AI settings" is the third target instead of timer; noted in Task 3 and flagged for the user.
- Mobile fixes: `.grid-2`, timer grids, weekly grid, scrollable timer/history tables (spec §5) → Task 4. The Today inline `min-width` children need no edit — their container `.jab-form` already has `flex-wrap: wrap`, so they reflow; adding a change there would be a no-op.
- Verification (spec) → each task's check/lint/test + manual steps.
- Non-goals respected: no component restructuring, no theme-toggle change, no chart rework, no body-font change, no blanket button conversion.

**Placeholder scan:** No TBD/TODO. All edits give exact old→new strings or exact commands. The table-wrap steps describe adding a wrapper around an unchanged inner block (its full inner markup isn't repeated because the instruction is "wrap, preserve inner exactly" — the anchors are the `<table>`/`</table>` lines).

**Type consistency:** No types/functions introduced. Class names are consistent between definition and use: `.btn-primary` (app.css Task 3 ↔ chat/login/settings Task 3), `.table-scroll` (app.css Task 4 step 1 ↔ timer Task 4 step 3 ↔ history Task 4 step 5). Breakpoint `640px` used consistently.
