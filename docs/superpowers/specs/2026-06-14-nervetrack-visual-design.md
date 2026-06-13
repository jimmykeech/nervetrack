# NerveTrack Visual Design System — "Still Water"

## Context

NerveTrack currently uses a generic cool dark dashboard theme (`frontend/src/app.css`).
It works but has no point of view. This spec defines a distinctive, intentional visual
identity — **"Still Water"** — and the work to apply it across the app.

Direction was chosen interactively (visual companion): a **calm, warm, journal-like**
aesthetic with **Fraunces** serif headings, shipped in **both light and dark modes**.
Two product-specific rules drive the palette:

- **Sitting time is red, standing time is green.** Prolonged sitting is the single
  biggest symptom aggravator; standing is the desired behaviour. Posture time is the
  app's most important signal, so it is colour-coded semantically everywhere it appears.
- **One semantic colour language.** The same refined red / amber / green express both
  daily **status** (R/A/G) and **posture** (sitting/standing), so across the whole app
  red always means "aggravating" and green always means "good."

Scope is **visual only**: no new pages, no changed data flow, no feature changes. The
deliverables are a token layer, a light/dark theme mechanism, posture colour-coding, a
reusable ratio bar, and per-component restyling.

## Aesthetic principles

1. **Calm over busy.** Generous spacing, soft contrast, one idea per card. This is a tool
   used daily, often in discomfort — it should feel restful, not clinical-cold or loud.
2. **Warm, not neutral.** Paper-warm light mode; espresso-warm dark mode. No pure white,
   no blue-black, no `#000`.
3. **Serif voice.** Fraunces for titles and large numerals gives a considered, journal
   feel and avoids generic AI/system-font aesthetics. Hanken Grotesk carries the UI.
4. **Colour means something.** Colour is reserved for semantics (status, posture). Neutral
   surfaces elsewhere so the meaningful colour reads.
5. **Quiet motion.** Subtle, purposeful — one orchestrated page-load reveal; gentle state
   transitions; nothing decorative or distracting.

## Typography

Self-hosted via Fontsource (offline-friendly for the Docker stack — no external font CDN):
add `@fontsource-variable/fraunces` and `@fontsource-variable/hanken-grotesk`, imported
once in `+layout.svelte`.

- **Display / headings & large numerals:** Fraunces (variable, optical sizing), weight 500–600.
- **Body / UI:** Hanken Grotesk, weight 400–700.
- **Never:** Inter, Roboto, Arial, system-ui as the primary face.

Type scale (mobile-first; rem):

| Token | Font / weight | Size | Use |
|---|---|---|---|
| `--t-display` | Fraunces 600 | 2.4rem | Page title ("Today"), login wordmark |
| `--t-h1` | Fraunces 600 | 1.9rem | Page headings |
| `--t-h2` | Fraunces 600 | 1.3rem | Card / section titles |
| `--t-label` | Hanken 600, uppercase, 0.14em tracking | 0.7rem | Stat labels, kickers, captions |
| `--t-body` | Hanken 400/500 | 1rem (1.55 lh) | Body, inputs, notes |
| `--t-small` | Hanken 500 | 0.85rem | Secondary text |
| `--t-stat` | Fraunces 600 | 1.9rem | Metric values (worst pain, tingling, sleep) |
| `--t-clock` | Hanken 700, `tabular-nums` | 3rem (Timer page) | Running timer clock |

All numeric values (metrics, durations, totals, clock) use `font-variant-numeric: tabular-nums`.

## Colour tokens

Defined as CSS variables on `:root` (dark = default) with a `[data-theme="light"]` override.
Both modes share token *names*; only values differ.

### Neutrals & surfaces

| Token | Light | Dark | Use |
|---|---|---|---|
| `--bg` | `#f1ebdf` | `#1a1713` | Page background |
| `--surface` | `#faf5ec` | `#221d16` | Cards |
| `--surface-2` | `#ece4d4` | `#2a241b` | Inset: inputs, pills, posture block |
| `--border` | `#e0d7c5` | `#342c20` | Hairlines, card borders |
| `--text` | `#38423a` | `#ece2d3` | Primary text / headings |
| `--text-muted` | `#8c9486` | `#9b9482` | Labels, secondary |
| `--text-faint` | `#a9af9f` | `#6f6a5c` | Placeholders, disabled |
| `--accent` | `#bd8a55` | `#cfa56a` | Brand, links, focus ring, active controls (clay) |
| `--shadow` | `0 2px 10px rgba(74,58,30,.08)` | `0 2px 10px rgba(0,0,0,.25)` | Card lift |

### Semantic (status R/A/G + posture)

| Token | Light | Dark | Meaning |
|---|---|---|---|
| `--good` | `#5f8a5f` | `#85ad7f` | Status G · **Standing** |
| `--caution` | `#c79a4a` | `#cdb06a` | Status A |
| `--bad` | `#b0524a` | `#d7705f` | Status R · **Sitting** |
| `--rest` | `#6e80a0` | `#7e90b2` | Posture: lying |
| `--move` | `#b9863f` | `#cda35e` | Posture: walking |

Posture mapping is fixed: `sitting → --bad`, `standing → --good`, `lying → --rest`,
`walking → --move`. Each semantic colour gets a low-alpha tint variant (e.g.
`--good-soft`) for pill/badge backgrounds, derived with `color-mix(in srgb, var(--good) 16%, transparent)`.

### Geometry & elevation

`--r-sm: 8px · --r: 12px · --r-lg: 16px · --r-pill: 999px`. Spacing scale on a 4px base
(`--sp-1: .25rem … --sp-8: 2rem`). Cards: `--surface`, `1px solid --border`, `--r-lg`,
`--shadow` (light) / border-only lift (dark).

## Theme mechanism

- Tokens switch on `document.documentElement[data-theme]` = `"light"` | `"dark"`.
- **First visit:** follow `prefers-color-scheme`. **After toggle:** persist choice in
  `localStorage["nervetrack-theme"]`.
- **Anti-flash:** a tiny inline script in `app.html` sets `data-theme` from
  localStorage/system *before* first paint (the app is SSR-off, so this avoids a flash).
- **Toggle control:** a sun/moon `ThemeToggle` in the header (and mirrored in Settings).
- New `frontend/src/lib/stores/theme.svelte.ts`: reads initial value, exposes
  `theme`, `setTheme()`, `toggle()`, writes the attribute + localStorage.

## Components

Most components inherit from tokens; the changes below are the targeted ones.

- **Cards** — warm `--surface`, `--r-lg`, soft shadow, `--sp-5` padding.
- **Buttons** — `primary` (clay `--accent` fill, contrast text), `secondary` (`--surface-2`
  + border), `ghost`. Focus-visible ring in `--accent`.
- **StatusToggle (G/A/R)** — segmented pills; inactive `--surface-2`/`--text-muted`,
  active filled with its semantic colour (`--good`/`--caution`/`--bad`).
- **Stepper** — inset `--surface-2`, Fraunces value, ghost +/− buttons.
- **Inputs / textarea** — `--surface-2`, `--border`, focus ring `--accent`; comfortable
  line-height for the notes field.
- **Nav (`+layout`)** — Fraunces wordmark; pill tabs (active = `--surface` + border);
  right side: `ThemeToggle` + account email + Sign out.
- **RatioBar (new, `lib/components/RatioBar.svelte`)** — horizontal stacked bar of posture
  durations, each segment coloured by its posture token, with the sit:stand ratio label.
  Reused on Today (sit vs stand) and Timer (all postures). The headline glanceable element.
- **Posture map (`lib/posture.ts`)** — single source for posture → `{label, cssVar}` so the
  store, RatioBar, Timer buttons, and charts agree.
- **LineChart** — read token values from CSS at render so charts are theme-aware (re-render
  on theme change). Dataset colours: pain → `--bad`, worst pain → `--caution`, tingling →
  `--accent`, intensity → `--good`; sitting bars → `--bad`, standing bars → `--good`. Axis
  ticks `--text-muted`, grid `--border`.

## Per-page treatment

- **Login** — full-bleed Still Water; Fraunces "NerveTrack" wordmark; warm-styled Google
  button; invite/error notice in `--bad-soft`.
- **Today** — Fraunces "Today"; StatusToggle; stat steppers (worst pain / tingling / sleep)
  with Fraunces numerals; **posture block with RatioBar** (sitting red, standing green);
  notes; gentle autosave indicator (`--good` on save).
- **Timer** — hero clock (`--t-clock`) tinted by the *current posture's* colour; posture
  buttons tinted by their tokens; per-posture totals grid + RatioBar; timeline list;
  sitting nudge as a gentle `--caution` glow (not alarming).
- **History** — charts in semantic colours; entry table with a status dot per row.
- **Exercises** — warm session form; progression chart in `--accent`/`--good`.
- **Weekly** — metric grid; trend + status badges in semantic colours.
- **Settings** — account card, **ThemeToggle**, import.

## Motion

- Transitions: colour/bg 150ms, transforms 200ms, easing `cubic-bezier(.2,.7,.2,1)`.
- **Page load:** one orchestrated reveal — cards fade + rise 10px with staggered
  `animation-delay` (≈40ms steps). Calm, not bouncy.
- Saved indicator fades in/out; active posture button has a soft pulse; sitting nudge
  fades up.
- **`prefers-reduced-motion: reduce`** disables transforms, stagger, and the pulse.

## Accessibility

- Body and label text meet WCAG AA (≥4.5:1) on their surfaces in both modes; verify the
  muted/faint tokens against `--bg`/`--surface` and tune if short.
- **Never colour-only:** status keeps letters (G/A/R), posture keeps text labels, RatioBar
  shows durations, charts keep legends — red/green is reinforced, never the sole signal.
- `:focus-visible` ring (`--accent`, 2px, 2px offset) on all interactive elements.
- Minimum 44px tap targets on mobile (posture buttons, toggles, steppers).

## Affected files

**Core**
- `frontend/src/app.css` — replace the palette with the token layer + base element styles (largest change).
- `frontend/src/app.html` — anti-flash theme bootstrap script.
- `frontend/package.json` — add `@fontsource-variable/fraunces`, `@fontsource-variable/hanken-grotesk`.

**New**
- `frontend/src/lib/stores/theme.svelte.ts` — theme store + persistence.
- `frontend/src/lib/components/ThemeToggle.svelte` — sun/moon toggle.
- `frontend/src/lib/components/RatioBar.svelte` — posture ratio bar.
- `frontend/src/lib/posture.ts` — posture → label/colour map.

**Edit**
- `frontend/src/routes/+layout.svelte` — import fonts, init theme, add ThemeToggle + Fraunces wordmark.
- `frontend/src/lib/components/{StatusToggle,Stepper,LineChart}.svelte` — token-based restyle; LineChart theme-aware colours.
- `frontend/src/routes/{+page,timer,history,exercises,weekly,settings,login}/+page.svelte` —
  apply RatioBar + posture colours where posture appears; otherwise mostly inherit tokens
  (targeted per-page tweaks only).

## Non-goals (YAGNI)

No layout/IA changes, no new pages, no functional changes, no animation library (CSS-only),
no per-user theme persistence on the backend (localStorage is enough for Phase 1).

## Verification

- `npm run build`, `npm run check` (0/0), `npx eslint .`, `npx prettier --check .`, `npx vitest run` all green.
- Toggle light/dark with no flash on reload; choice persists; first visit follows system.
- Today + Timer show sitting in red / standing in green and a correct RatioBar; charts
  recolour on theme switch.
- Manual pass in the running stack (http://localhost:3000) across all pages in both modes;
  spot-check contrast and `prefers-reduced-motion`.
