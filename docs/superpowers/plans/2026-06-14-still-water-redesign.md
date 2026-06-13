# Still Water Visual Redesign — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reskin NerveTrack with the warm "Still Water" aesthetic — light + dark modes, Fraunces/Hanken type, a single red/amber/green semantic colour language, and posture colour-coding (sitting red, standing green) — without changing any behaviour.

**Architecture:** A CSS custom-property token layer in `app.css` drives everything; light/dark switch via a `data-theme` attribute on `<html>` (anti-flash bootstrap in `app.html`, a tiny rune store for the toggle). Pure logic (theme resolution, posture map, ratio math) lives in testable `.ts` modules; Svelte components consume them. Pages mostly inherit from tokens — only posture-coloured surfaces and charts need per-file edits.

**Tech Stack:** SvelteKit 2 + Svelte 5 runes, TypeScript, plain CSS custom properties, `@fontsource-variable/*` (offline fonts), Chart.js, Vitest.

**Branch:** `design/still-water` (app baseline already committed). Commit after every task.

**Verification gates** (the project's "tests" for visual work — run from `frontend/`):
`npm run check` (svelte-check, expect `0 errors 0 warnings`), `npm run build`, `npx vitest run`, `npx eslint .`, `npx prettier --check .`.

---

## File structure

**New**
- `frontend/src/lib/theme.ts` — pure theme helpers (resolve initial, next).
- `frontend/src/lib/stores/theme.svelte.ts` — rune store: applies `data-theme`, persists.
- `frontend/src/lib/components/ThemeToggle.svelte` — sun/moon button.
- `frontend/src/lib/posture.ts` — posture → `{label, cssVar}` map + `postureColor()`.
- `frontend/src/lib/ratio.ts` — pure `ratioSegments()` for the bar.
- `frontend/src/lib/components/RatioBar.svelte` — posture ratio bar.
- Tests: `frontend/src/lib/theme.test.ts`, `posture.test.ts`, `ratio.test.ts`.

**Modify**
- `frontend/package.json` — add the two Fontsource packages.
- `frontend/src/app.html` — anti-flash theme script.
- `frontend/src/app.css` — full token layer + base styles + typography + motion (replaces current palette).
- `frontend/src/routes/+layout.svelte` — font imports, theme init, ThemeToggle, Fraunces wordmark.
- `frontend/src/lib/components/{StatusToggle,Stepper,LineChart}.svelte` — token restyle; chart theme-aware.
- `frontend/src/routes/+page.svelte` (Today), `timer/+page.svelte`, `history/+page.svelte`,
  `exercises/+page.svelte`, `weekly/+page.svelte`, `settings/+page.svelte`, `login/+page.svelte` — posture colours, RatioBar, ThemeToggle, minor token tweaks.

---

## Task 1: Install offline fonts

**Files:**
- Modify: `frontend/package.json`
- Modify: `frontend/src/routes/+layout.svelte:1-3` (script imports)

- [ ] **Step 1: Install the Fontsource variable packages**

Run (from `frontend/`):
```bash
npm install @fontsource-variable/fraunces@^5 @fontsource-variable/hanken-grotesk@^5
```
Expected: both added to `package.json` `dependencies`.

- [ ] **Step 2: Confirm the CSS font-family names**

Run:
```bash
grep -h "font-family" node_modules/@fontsource-variable/fraunces/index.css node_modules/@fontsource-variable/hanken-grotesk/index.css | head
```
Expected: `'Fraunces Variable'` and `'Hanken Grotesk Variable'`. If they differ, use the printed names in Task 4's `--font-display`/`--font-ui`.

- [ ] **Step 3: Import the fonts once, at the top of the root layout**

In `frontend/src/routes/+layout.svelte`, add to the very top of the `<script lang="ts">` block (before `import '../app.css';`):
```ts
import '@fontsource-variable/fraunces';
import '@fontsource-variable/hanken-grotesk';
```

- [ ] **Step 4: Verify build picks up the fonts**

Run: `npm run build`
Expected: build succeeds; no "cannot resolve" errors for the font packages.

- [ ] **Step 5: Commit**

```bash
git add frontend/package.json frontend/package-lock.json frontend/src/routes/+layout.svelte
git commit -m "feat(design): add Fraunces + Hanken Grotesk offline fonts"
```

---

## Task 2: Pure theme helpers (TDD)

**Files:**
- Create: `frontend/src/lib/theme.ts`
- Test: `frontend/src/lib/theme.test.ts`

- [ ] **Step 1: Write the failing test**

`frontend/src/lib/theme.test.ts`:
```ts
import { describe, expect, it } from 'vitest';
import { resolveInitialTheme, nextTheme } from './theme';

describe('resolveInitialTheme', () => {
  it('uses a valid stored value over system', () => {
    expect(resolveInitialTheme('light', 'dark')).toBe('light');
    expect(resolveInitialTheme('dark', 'light')).toBe('dark');
  });
  it('falls back to system when stored is missing/invalid', () => {
    expect(resolveInitialTheme(null, 'light')).toBe('light');
    expect(resolveInitialTheme('purple', 'dark')).toBe('dark');
  });
});

describe('nextTheme', () => {
  it('toggles', () => {
    expect(nextTheme('light')).toBe('dark');
    expect(nextTheme('dark')).toBe('light');
  });
});
```

- [ ] **Step 2: Run it, expect fail**

Run: `npx vitest run src/lib/theme.test.ts`
Expected: FAIL — cannot resolve `./theme`.

- [ ] **Step 3: Implement**

`frontend/src/lib/theme.ts`:
```ts
export type Theme = 'light' | 'dark';

export function resolveInitialTheme(stored: string | null, system: Theme): Theme {
  return stored === 'light' || stored === 'dark' ? stored : system;
}

export function nextTheme(t: Theme): Theme {
  return t === 'light' ? 'dark' : 'light';
}
```

- [ ] **Step 4: Run it, expect pass**

Run: `npx vitest run src/lib/theme.test.ts`
Expected: PASS (5 assertions).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/theme.ts frontend/src/lib/theme.test.ts
git commit -m "feat(design): pure theme resolution helpers"
```

---

## Task 3: Theme store (applies attribute + persists)

**Files:**
- Create: `frontend/src/lib/stores/theme.svelte.ts`

- [ ] **Step 1: Implement the store**

`frontend/src/lib/stores/theme.svelte.ts`:
```ts
// Applies the chosen theme to <html data-theme> and persists the user's choice.
// First visit follows the OS preference; an explicit toggle is remembered.

import { resolveInitialTheme, nextTheme, type Theme } from '$lib/theme';

const KEY = 'nervetrack-theme';

export const themeState = $state<{ theme: Theme }>({ theme: 'dark' });

function systemTheme(): Theme {
  return window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark';
}

function apply(t: Theme): void {
  themeState.theme = t;
  document.documentElement.setAttribute('data-theme', t);
}

export function initTheme(): void {
  apply(resolveInitialTheme(localStorage.getItem(KEY), systemTheme()));
}

export function toggleTheme(): void {
  const t = nextTheme(themeState.theme);
  apply(t);
  localStorage.setItem(KEY, t); // only an explicit choice is persisted
}
```

- [ ] **Step 2: Type-check**

Run: `npm run check`
Expected: `0 errors`. (Store not yet imported anywhere — that's fine.)

- [ ] **Step 3: Commit**

```bash
git add frontend/src/lib/stores/theme.svelte.ts
git commit -m "feat(design): theme store with data-theme + persistence"
```

---

## Task 4: Token layer + base styles in app.css

**Files:**
- Modify: `frontend/src/app.css` (full replace)

- [ ] **Step 1: Replace `app.css` with the Still Water token layer**

Overwrite `frontend/src/app.css` with:
```css
/* ---------- Still Water design tokens ---------- */
/* Dark is the default (:root); light overrides via [data-theme="light"]. */
:root {
  --font-display: 'Fraunces Variable', Georgia, 'Times New Roman', serif;
  --font-ui: 'Hanken Grotesk Variable', system-ui, -apple-system, sans-serif;

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

  /* posture semantics (sitting aggravates → red, standing is good → green) */
  --posture-sitting: var(--bad);
  --posture-standing: var(--good);
  --posture-lying: var(--rest);
  --posture-walking: var(--move);

  /* low-alpha tints for pill/badge backgrounds */
  --good-soft: color-mix(in srgb, var(--good) 16%, transparent);
  --caution-soft: color-mix(in srgb, var(--caution) 16%, transparent);
  --bad-soft: color-mix(in srgb, var(--bad) 16%, transparent);
  --accent-soft: color-mix(in srgb, var(--accent) 16%, transparent);

  --r-sm: 8px;
  --r: 12px;
  --r-lg: 16px;
  --r-pill: 999px;
  --maxw: 760px;

  color-scheme: dark;
  font-family: var(--font-ui);
}

[data-theme='light'] {
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
  color-scheme: light;
}

* { box-sizing: border-box; }

html, body { margin: 0; padding: 0; }
body {
  background: var(--bg);
  color: var(--text);
  font-family: var(--font-ui);
  -webkit-font-smoothing: antialiased;
  transition: background 0.2s ease, color 0.2s ease;
}

a { color: var(--accent); text-decoration: none; }

h1, h2, h3 {
  font-family: var(--font-display);
  font-weight: 600;
  line-height: 1.15;
  letter-spacing: -0.01em;
  color: var(--text);
}

button {
  font: inherit;
  cursor: pointer;
  border: 1px solid var(--border);
  background: var(--surface-2);
  color: var(--text);
  border-radius: 10px;
  padding: 0.55rem 0.9rem;
  transition: background 0.12s ease, border-color 0.12s ease, transform 0.12s ease;
}
button:hover { background: var(--border); }
button:disabled { opacity: 0.5; cursor: default; }
:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }

input, textarea, select {
  font: inherit;
  background: var(--surface-2);
  color: var(--text);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 0.5rem 0.6rem;
  width: 100%;
}
input::placeholder, textarea::placeholder { color: var(--text-faint); }
input[type='checkbox'] { width: auto; accent-color: var(--accent); }
input:focus-visible, textarea:focus-visible, select:focus-visible {
  outline: none; border-color: var(--accent); box-shadow: 0 0 0 2px var(--accent-soft);
}
textarea { resize: vertical; min-height: 7rem; line-height: 1.55; }

label { display: block; font-size: 0.85rem; color: var(--text-muted); margin-bottom: 0.25rem; }

.card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--r-lg);
  padding: 1.1rem;
  margin-bottom: 1rem;
  box-shadow: var(--shadow);
}

.row { display: flex; gap: 0.75rem; flex-wrap: wrap; }
.field { flex: 1 1 8rem; margin-bottom: 0.75rem; }
.grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 0.75rem; }

.muted { color: var(--text-muted); }
.small { font-size: 0.85rem; }
.label-caps {
  font-size: 0.7rem; letter-spacing: 0.14em; text-transform: uppercase; color: var(--text-muted);
}

/* status / semantic fills */
.status-G { background: var(--good); color: #11240f; border-color: var(--good); }
.status-A { background: var(--caution); color: #2c1f00; border-color: var(--caution); }
.status-R { background: var(--bad); color: #2a0c08; border-color: var(--bad); }

.pill {
  display: inline-block; padding: 0.15rem 0.55rem; border-radius: var(--r-pill);
  font-size: 0.78rem; font-weight: 600; border: 1px solid var(--border);
}

table { width: 100%; border-collapse: collapse; font-size: 0.9rem; }
th, td { text-align: left; padding: 0.5rem; border-bottom: 1px solid var(--border); }
th { color: var(--text-muted); font-weight: 600; }

.saved { font-size: 0.8rem; color: var(--good); }
.saving { font-size: 0.8rem; color: var(--text-muted); }

/* tabular numerals everywhere numbers matter */
.tnum { font-variant-numeric: tabular-nums; }

/* ---------- motion: one calm page-load reveal ---------- */
main > .card { animation: sw-rise 0.4s both; }
main > .card:nth-child(2) { animation-delay: 0.04s; }
main > .card:nth-child(3) { animation-delay: 0.08s; }
main > .card:nth-child(4) { animation-delay: 0.12s; }
main > .card:nth-child(5) { animation-delay: 0.16s; }
main > .card:nth-child(n + 6) { animation-delay: 0.2s; }
@keyframes sw-rise {
  from { opacity: 0; transform: translateY(10px); }
  to { opacity: 1; transform: none; }
}
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { animation: none !important; transition: none !important; }
}
```

- [ ] **Step 2: Type-check + build**

Run: `npm run check && npm run build`
Expected: `0 errors`; build succeeds.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/app.css
git commit -m "feat(design): Still Water token layer, base styles, motion"
```

---

## Task 5: Anti-flash theme bootstrap

**Files:**
- Modify: `frontend/src/app.html`

- [ ] **Step 1: Add the pre-paint theme script**

In `frontend/src/app.html`, immediately after `<head>` and before `%sveltekit.head%`, insert:
```html
<script>
  (function () {
    try {
      var k = 'nervetrack-theme', s = localStorage.getItem(k);
      var sys = window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark';
      document.documentElement.setAttribute('data-theme', s === 'light' || s === 'dark' ? s : sys);
    } catch (e) {
      document.documentElement.setAttribute('data-theme', 'dark');
    }
  })();
</script>
```

- [ ] **Step 2: Build**

Run: `npm run build`
Expected: success.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/app.html
git commit -m "feat(design): anti-flash theme bootstrap in app.html"
```

---

## Task 6: ThemeToggle component + wire into layout

**Files:**
- Create: `frontend/src/lib/components/ThemeToggle.svelte`
- Modify: `frontend/src/routes/+layout.svelte`

- [ ] **Step 1: Create the toggle**

`frontend/src/lib/components/ThemeToggle.svelte`:
```svelte
<script lang="ts">
  import { themeState, toggleTheme } from '$lib/stores/theme.svelte';
</script>

<button class="theme" onclick={toggleTheme} aria-label="Toggle light/dark theme" title="Toggle theme">
  {themeState.theme === 'dark' ? '☾' : '☀'}
</button>

<style>
  .theme {
    width: 2.2rem;
    height: 2.2rem;
    padding: 0;
    border-radius: var(--r-pill);
    font-size: 1rem;
    line-height: 1;
  }
</style>
```

- [ ] **Step 2: Init theme + add the toggle + serif wordmark in the layout**

In `frontend/src/routes/+layout.svelte`:
- Add imports near the other imports:
```ts
import ThemeToggle from '$lib/components/ThemeToggle.svelte';
import { initTheme } from '$lib/stores/theme.svelte';
```
- In the existing `onMount(async () => { ... })`, add `initTheme();` as the **first** line.
- In the header's `.topline`, place `<ThemeToggle />` just before the `{#if auth.user}` account block so it always shows:
```svelte
<div class="topline">
  <div class="brand">NerveTrack</div>
  <div class="account">
    <ThemeToggle />
    {#if auth.user}
      <span class="muted small">{auth.user.email}</span>
      <button class="logout" onclick={handleLogout}>Sign out</button>
    {/if}
  </div>
</div>
```
- Give the brand the display font — add to the `<style>` block:
```css
.brand { font-family: var(--font-display); }
```
(If `.account` is not already a flex row, ensure: `.account { display: flex; align-items: center; gap: 0.6rem; }` — it already is.)

- [ ] **Step 3: Verify**

Run: `npm run check && npm run build`
Expected: `0 errors`; build succeeds.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/lib/components/ThemeToggle.svelte frontend/src/routes/+layout.svelte
git commit -m "feat(design): theme toggle + serif wordmark in header"
```

---

## Task 7: Posture colour map (TDD)

**Files:**
- Create: `frontend/src/lib/posture.ts`
- Test: `frontend/src/lib/posture.test.ts`

- [ ] **Step 1: Write the failing test**

`frontend/src/lib/posture.test.ts`:
```ts
import { describe, expect, it } from 'vitest';
import { POSTURE_META, postureColor } from './posture';

describe('posture map', () => {
  it('covers all four postures with labels', () => {
    expect(Object.keys(POSTURE_META).sort()).toEqual(['lying', 'sitting', 'standing', 'walking']);
    expect(POSTURE_META.sitting.label).toBe('Sitting');
  });
  it('returns a css var() referencing the posture token', () => {
    expect(postureColor('sitting')).toBe('var(--posture-sitting)');
    expect(postureColor('standing')).toBe('var(--posture-standing)');
  });
});
```

- [ ] **Step 2: Run it, expect fail**

Run: `npx vitest run src/lib/posture.test.ts`
Expected: FAIL — cannot resolve `./posture`.

- [ ] **Step 3: Implement**

`frontend/src/lib/posture.ts`:
```ts
import type { Posture } from '$lib/types';

export const POSTURE_META: Record<Posture, { label: string; cssVar: string }> = {
  sitting: { label: 'Sitting', cssVar: '--posture-sitting' },
  standing: { label: 'Standing', cssVar: '--posture-standing' },
  lying: { label: 'Lying', cssVar: '--posture-lying' },
  walking: { label: 'Walking', cssVar: '--posture-walking' }
};

export function postureColor(p: Posture): string {
  return `var(${POSTURE_META[p].cssVar})`;
}
```

- [ ] **Step 4: Run it, expect pass**

Run: `npx vitest run src/lib/posture.test.ts`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/posture.ts frontend/src/lib/posture.test.ts
git commit -m "feat(design): posture colour/label map"
```

---

## Task 8: Ratio segments (TDD)

**Files:**
- Create: `frontend/src/lib/ratio.ts`
- Test: `frontend/src/lib/ratio.test.ts`

- [ ] **Step 1: Write the failing test**

`frontend/src/lib/ratio.test.ts`:
```ts
import { describe, expect, it } from 'vitest';
import { ratioSegments } from './ratio';

describe('ratioSegments', () => {
  it('returns [] when nothing is tracked', () => {
    expect(ratioSegments({ sitting: 0, standing: 0, lying: 0, walking: 0 })).toEqual([]);
  });
  it('computes percentages in posture order, skipping zeros', () => {
    const segs = ratioSegments({ sitting: 300, standing: 100, lying: 0, walking: 0 });
    expect(segs.map((s) => s.posture)).toEqual(['sitting', 'standing']);
    expect(segs[0].percent).toBeCloseTo(75);
    expect(segs[1].percent).toBeCloseTo(25);
    expect(segs.reduce((t, s) => t + s.percent, 0)).toBeCloseTo(100);
  });
});
```

- [ ] **Step 2: Run it, expect fail**

Run: `npx vitest run src/lib/ratio.test.ts`
Expected: FAIL — cannot resolve `./ratio`.

- [ ] **Step 3: Implement**

`frontend/src/lib/ratio.ts`:
```ts
import type { Posture, PostureTotals } from '$lib/types';

export interface RatioSegment {
  posture: Posture;
  seconds: number;
  percent: number;
}

const ORDER: Posture[] = ['sitting', 'standing', 'lying', 'walking'];

export function ratioSegments(totals: PostureTotals): RatioSegment[] {
  const total = ORDER.reduce((sum, p) => sum + totals[p], 0);
  if (total === 0) return [];
  return ORDER.filter((p) => totals[p] > 0).map((p) => ({
    posture: p,
    seconds: totals[p],
    percent: (totals[p] / total) * 100
  }));
}
```

- [ ] **Step 4: Run it, expect pass**

Run: `npx vitest run src/lib/ratio.test.ts`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/ratio.ts frontend/src/lib/ratio.test.ts
git commit -m "feat(design): posture ratio segment math"
```

---

## Task 9: RatioBar component

**Files:**
- Create: `frontend/src/lib/components/RatioBar.svelte`

- [ ] **Step 1: Create the component**

`frontend/src/lib/components/RatioBar.svelte`:
```svelte
<script lang="ts">
  import type { PostureTotals } from '$lib/types';
  import { ratioSegments } from '$lib/ratio';
  import { POSTURE_META, postureColor } from '$lib/posture';
  import { formatMinutesish, sitStandRatio } from '$lib/time';

  let { totals, showHeader = true }: { totals: PostureTotals; showHeader?: boolean } = $props();
  const segments = $derived(ratioSegments(totals));
</script>

<div class="ratiobar">
  {#if showHeader}
    <div class="label-caps">Posture today · sit : stand {sitStandRatio(totals)}</div>
  {/if}
  <div class="bar">
    {#each segments as s (s.posture)}
      <div
        class="seg"
        style="width:{s.percent}%; background:{postureColor(s.posture)}"
        title="{POSTURE_META[s.posture].label} {formatMinutesish(s.seconds)}"
      ></div>
    {/each}
    {#if segments.length === 0}<div class="seg empty"></div>{/if}
  </div>
  <div class="legend">
    <span class="sit tnum">Sitting {formatMinutesish(totals.sitting)}</span>
    <span class="stand tnum">Standing {formatMinutesish(totals.standing)}</span>
  </div>
</div>

<style>
  .ratiobar { display: flex; flex-direction: column; gap: 0.55rem; }
  .bar {
    display: flex;
    height: 10px;
    border-radius: var(--r-sm);
    overflow: hidden;
    background: var(--surface-2);
  }
  .seg { height: 100%; }
  .seg.empty { width: 100%; background: var(--surface-2); }
  .legend { display: flex; justify-content: space-between; font-size: 0.85rem; }
  .sit { color: var(--posture-sitting); font-weight: 600; }
  .stand { color: var(--posture-standing); font-weight: 600; }
</style>
```

- [ ] **Step 2: Verify**

Run: `npm run check`
Expected: `0 errors`.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/lib/components/RatioBar.svelte
git commit -m "feat(design): RatioBar posture component"
```

---

## Task 10: StatusToggle + Stepper restyle

**Files:**
- Modify: `frontend/src/lib/components/StatusToggle.svelte` (`<style>` only)
- Modify: `frontend/src/lib/components/Stepper.svelte` (`<style>` only)

- [ ] **Step 1: StatusToggle — active pill uses its semantic colour**

The markup already applies `status-{key}` classes on the active option (now token-coloured via `app.css`). Replace the StatusToggle `<style>` block with:
```css
.toggle { display: flex; gap: 0.5rem; }
.opt {
  flex: 1;
  font-weight: 600;
  background: var(--surface-2);
  color: var(--text-muted);
  border-radius: var(--r-pill);
}
.opt.on { transform: translateY(-1px); color: inherit; }
```

- [ ] **Step 2: Stepper — serif value, inset controls**

Replace the Stepper `<style>` block with:
```css
.controls { display: flex; align-items: center; gap: 0.5rem; }
.value {
  min-width: 2.5rem;
  text-align: center;
  font-family: var(--font-display);
  font-variant-numeric: tabular-nums;
  font-size: 1.35rem;
  color: var(--text);
}
.value.unset { color: var(--text-faint); }
.clear { padding: 0.3rem 0.5rem; font-size: 0.8rem; }
button { min-width: 2.4rem; }
```

- [ ] **Step 3: Verify**

Run: `npm run check && npm run build`
Expected: `0 errors`; build succeeds.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/lib/components/StatusToggle.svelte frontend/src/lib/components/Stepper.svelte
git commit -m "feat(design): restyle StatusToggle + Stepper on tokens"
```

---

## Task 11: Theme-aware charts

**Files:**
- Modify: `frontend/src/lib/components/LineChart.svelte`

LineChart currently hardcodes hex colours for axes/legend and receives dataset colours from pages. Make it read CSS tokens at render and re-render on theme change so both modes look right.

- [ ] **Step 1: Read tokens + observe theme changes**

In `frontend/src/lib/components/LineChart.svelte`:
- Add a helper at the top of the `<script>` (after imports):
```ts
function token(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || '#888';
}
```
- In the `options` object passed to `new Chart(...)`, replace the hardcoded colours:
  - `x.ticks.color` and `y.ticks.color` → `token('--text-muted')`
  - `y.grid.color` → `token('--border')`
  - `plugins.legend.labels.color` → `token('--text')`
- Re-render when `data-theme` flips. Inside `onMount`, after `render()`, add:
```ts
const observer = new MutationObserver(render);
observer.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
onDestroy(() => observer.disconnect());
```
(Keep the existing `$effect` that re-renders on `labels`/`datasets` changes.)

- [ ] **Step 2: Verify**

Run: `npm run check && npm run build`
Expected: `0 errors`; build succeeds.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/lib/components/LineChart.svelte
git commit -m "feat(design): theme-aware chart axis/legend colours"
```

---

## Task 12: Today page — RatioBar + posture colours

**Files:**
- Modify: `frontend/src/routes/+page.svelte`

- [ ] **Step 1: Use RatioBar for the posture totals**

In `frontend/src/routes/+page.svelte`:
- Add import: `import RatioBar from '$lib/components/RatioBar.svelte';`
- Replace the existing "Today's posture time" card body (the `<strong>` + `.muted` line listing sitting/standing/lying/walking) with:
```svelte
<div class="card totals">
  <RatioBar totals={totals} />
  <a href="/timer" class="small">Open timer →</a>
</div>
```
(`totals` is the existing `$derived` value — keep it. `formatMinutesish` may become unused; if `npm run check` flags it, remove it from the import.)

- [ ] **Step 2: Verify (and drop now-unused imports if check flags them)**

Run: `npm run check`
Expected: `0 errors` (resolve any "declared but never used" by removing that import).

- [ ] **Step 3: Commit**

```bash
git add frontend/src/routes/+page.svelte
git commit -m "feat(design): Today uses RatioBar for posture totals"
```

---

## Task 13: Timer page — posture colours on clock, buttons, totals

**Files:**
- Modify: `frontend/src/routes/timer/+page.svelte`

- [ ] **Step 1: Colour the live clock + posture buttons by posture**

In `frontend/src/routes/timer/+page.svelte`:
- Add imports:
```ts
import RatioBar from '$lib/components/RatioBar.svelte';
import { postureColor } from '$lib/posture';
```
- Tint the running clock with the current posture colour — on the `.clock` element when running, add an inline style:
```svelte
<div class="clock" style={running ? `color:${postureColor(running.posture)}` : ''}>
  {formatDuration(store.elapsed)}
</div>
```
- Tint each posture button by its own colour. Replace the posture `<button>` in the `{#each POSTURES as p}` loop with:
```svelte
<button
  class="pbtn {running?.posture === p ? 'active' : ''}"
  style={running?.posture === p ? `--pc:${postureColor(p)}` : `--pc:var(${postureColorVar(p)})`}
  onclick={() => pick(p)}
>
  {POSTURE_LABEL[p]}
</button>
```
  where you add this tiny local helper in the script:
```ts
import { POSTURE_META } from '$lib/posture';
function postureColorVar(p: import('$lib/types').Posture): string {
  return POSTURE_META[p].cssVar;
}
```
- Update `.pbtn.active` style to use the posture colour, and give the totals cells their posture colour. In the `<style>` block replace `.pbtn.active { ... }` with:
```css
.pbtn.active { background: var(--pc); border-color: var(--pc); color: #1c130a; }
.tval { color: var(--text); }
```
- Add a RatioBar under the totals grid. After the `.ratio` div inside `.card.totals`, add:
```svelte
<div style="margin-top: 0.9rem"><RatioBar totals={totals} showHeader={false} /></div>
```

- [ ] **Step 2: Verify**

Run: `npm run check && npm run build`
Expected: `0 errors`; build succeeds.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/routes/timer/+page.svelte
git commit -m "feat(design): posture-coloured clock, buttons, ratio on Timer"
```

---

## Task 14: History page — semantic chart colours + status dots

**Files:**
- Modify: `frontend/src/routes/history/+page.svelte`

- [ ] **Step 1: Map chart dataset colours to tokens**

In `frontend/src/routes/history/+page.svelte`, add a token reader near the top of the `<script>`:
```ts
function token(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || '#888';
}
```
- In `painDatasets`, change the `ds(...)` colour args:
  - Sharp pain episodes → `token('--bad')`
  - Worst pain → `token('--caution')`
  - Tingling level → `token('--accent')`
  - Session intensity → `token('--good')`
- In `postureDatasets`, set:
  - Sitting bars `backgroundColor: token('--posture-sitting')`
  - Standing bars `backgroundColor: token('--posture-standing')`
- Make these `$derived` so they recompute on theme change (they already are `$derived`; the MutationObserver in LineChart re-renders, but recomputing here keeps colours correct — wrap the token reads so they run at access time, which `$derived` already does).

- [ ] **Step 2: Status dot in the entries table**

Replace the status `<td>` cell content with a coloured dot + letter:
```svelte
<td>
  {#if e.status}
    <span class="dot status-{e.status}"></span>{e.status}
  {:else}—{/if}
</td>
```
And add to the page `<style>`:
```css
.dot {
  display: inline-block; width: 9px; height: 9px; border-radius: 50%;
  margin-right: 0.4rem; vertical-align: 0;
}
```

- [ ] **Step 3: Verify**

Run: `npm run check && npm run build`
Expected: `0 errors`; build succeeds.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/routes/history/+page.svelte
git commit -m "feat(design): semantic chart colours + status dots on History"
```

---

## Task 15: Exercises, Weekly, Settings, Login polish

**Files:**
- Modify: `frontend/src/routes/exercises/+page.svelte`
- Modify: `frontend/src/routes/weekly/+page.svelte`
- Modify: `frontend/src/routes/settings/+page.svelte`
- Modify: `frontend/src/routes/login/+page.svelte`

These mostly inherit the tokens already. Targeted edits:

- [ ] **Step 1: Exercises — progression chart colours**

In `exercises/+page.svelte`, add the same `token()` helper (from Task 14 Step 1) and set the progression `progDatasets` colours: Difficulty → `token('--caution')`, Weight → `token('--accent')`. Verify `npm run check`.

- [ ] **Step 2: Weekly — status-coloured overall-status buttons**

In `weekly/+page.svelte`, the `{#each ['G','A','R']}` buttons already toggle `status-{s}`. No change needed beyond tokens; confirm the trend/status pills read well. (No code change required if visually fine — skip silently.)

- [ ] **Step 3: Settings — confirm ThemeToggle reachable**

The header ThemeToggle (Task 6) already covers theme switching app-wide. Optionally add a labelled toggle in the Account card:
```svelte
<script lang="ts">
  import ThemeToggle from '$lib/components/ThemeToggle.svelte';
</script>
```
and in the Account card body add: `<div class="row" style="align-items:center; gap:.6rem"><span class="small muted">Theme</span><ThemeToggle /></div>`

- [ ] **Step 4: Login — serif wordmark on warm surface**

In `login/+page.svelte`, give the `h1` the display font and warm the card. Add to its `<style>`:
```css
h1 { font-family: var(--font-display); }
.card { background: var(--surface); border: 1px solid var(--border); box-shadow: var(--shadow); }
```
(The Google button already contrasts on the warm surface; leave its white background.)

- [ ] **Step 5: Verify all**

Run: `npm run check && npm run build`
Expected: `0 errors`; build succeeds.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/routes/exercises/+page.svelte frontend/src/routes/weekly/+page.svelte frontend/src/routes/settings/+page.svelte frontend/src/routes/login/+page.svelte
git commit -m "feat(design): polish Exercises, Weekly, Settings, Login"
```

---

## Task 16: Full verification + manual pass

**Files:** none (verification only)

- [ ] **Step 1: Run the full gate**

Run (from `frontend/`):
```bash
npm run check && npx vitest run && npx eslint . && npx prettier --check . && npm run build
```
Expected: svelte-check `0 errors 0 warnings`; vitest all pass (existing time tests + new theme/posture/ratio); eslint clean; prettier clean; build succeeds. Fix anything that fails, then re-run.

- [ ] **Step 2: Manual pass in the running stack**

```bash
cd .. && docker compose up -d --build frontend
```
Open http://localhost:3000 and check, in BOTH themes (toggle in header):
- No flash of the wrong theme on reload; the choice persists; a fresh browser follows the OS setting.
- Today + Timer show **sitting red / standing green** and a correct RatioBar.
- History/Exercises charts recolour when you toggle theme.
- Login, Today, Timer, History, Exercises, Weekly, Settings all read well (contrast, spacing).
- Toggle OS "reduce motion" → the page-load rise animation is suppressed.

- [ ] **Step 3: Final commit (if Step 1 required fixes)**

```bash
git add -A && git commit -m "chore(design): final verification fixes"
```

---

## Self-review notes (author)

- **Spec coverage:** type system (T1,4,10), colour tokens light+dark (T4), theme mechanism (T2,3,5,6), posture colours + RatioBar (T7,8,9,12,13), charts (T11,14), per-page treatment (T12–15), motion + reduced-motion (T4), accessibility focus rings + non-colour cues — status letters/dots, posture labels (T4,9,14). All mapped.
- **Contrast risk** from the spec is exercised in T16 Step 2 (manual, both themes); tune `--text-muted`/`--text-faint` if any label is short of AA.
- **Type consistency:** `Theme`, `resolveInitialTheme`, `nextTheme` (T2) reused by store (T3); `POSTURE_META`/`postureColor` (T7) reused by RatioBar (T9) and Timer (T13); `ratioSegments`/`RatioSegment` (T8) reused by RatioBar (T9). `PostureTotals`/`Posture` come from existing `$lib/types`.
```
