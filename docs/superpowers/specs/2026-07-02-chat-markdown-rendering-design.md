# Chat: render LLM output as markdown

**Date:** 2026-07-02
**Status:** Draft — awaiting review

## Problem

The chat page renders assistant messages as plain text. In
`frontend/src/routes/chat/+page.svelte` the assistant bubble is
`<div class="bubble">{m.content}</div>` with `white-space: pre-wrap`.
Markdown emitted by the model — headings (`##`), bold (`**`), lists (`-`),
tables, and fenced code — is displayed literally instead of formatted, so
the output looks unstructured and hard to read.

## Goal

Render assistant (LLM) message content and the live streaming bubble as
formatted markdown, safely. User-typed messages remain plain text.

## Approach

Parse markdown to HTML with `marked`, sanitize the result with `DOMPurify`,
and insert it with Svelte's `{@html ...}`. Sanitization is required because
LLM output is untrusted and `{@html}` bypasses Svelte's escaping — this
closes the XSS surface.

### 1. Pure helper — `frontend/src/lib/markdown.ts`

Export `renderMarkdown(md: string | null): string`.

- Returns `''` when `md` is null or empty.
- Parses with `marked` in synchronous mode, GFM enabled (tables, fenced
  code, task lists, autolinks).
- Sanitizes the produced HTML with `DOMPurify`.
- Adds `target="_blank"` and `rel="noopener noreferrer"` to anchors (via a
  DOMPurify `afterSanitizeAttributes` hook or post-parse pass).

Kept UI-free and pure so it is unit-testable, mirroring the existing
`frontend/src/lib/chat.ts` convention.

### 2. Component changes — `frontend/src/routes/chat/+page.svelte`

- Import `renderMarkdown`.
- Assistant bubble: `{m.content}` → `{@html renderMarkdown(m.content)}`.
  Guard on role so only assistant messages are rendered as markdown; user
  messages keep `{m.content}` (plain text).
- Live streaming bubble: `{chat.streaming}` →
  `{@html renderMarkdown(chat.streaming)}` (markdown renders live as tokens
  arrive).
- The "Looking at your data…" tool bubble is unchanged.

### 3. Styling — scoped CSS in the component

Add rules under `.msg.assistant .bubble` for rendered markdown elements:

- Headings, `p`, `ul`/`ol`: sensible margins; remove top margin on the first
  child and bottom margin on the last child so bubbles don't gain stray
  padding.
- `code` / `pre`: monospace font, subtle background, wrap/scroll for long
  lines.
- `table`: collapsed borders, cell padding.
- `blockquote`, `a`: readable defaults consistent with the app theme
  variables (`--surface-2`, `--accent-soft`, etc.).

Keep `white-space: pre-wrap` on user bubbles only; markdown block elements
provide their own spacing, so it is removed from assistant bubbles to avoid
doubled blank lines.

### 4. Dependencies — `frontend/package.json`

- `dependencies`: add `marked`, `dompurify`.
- `devDependencies`: add `jsdom` (only so the helper's unit test can run —
  the vitest environment is `node` and DOMPurify needs a DOM).

### 5. Tests — `frontend/src/lib/markdown.test.ts`

New file with `// @vitest-environment jsdom` at the top. Cases:

- Heading `## Hi` → contains `<h2>`.
- Bold `**x**` → contains `<strong>`.
- List `- a\n- b` → contains `<ul>` and two `<li>`.
- Fenced code ` ```js\ncode\n``` ` → contains `<pre><code`.
- Sanitization: input containing `<script>` or a `javascript:` link is
  stripped from the output.
- Links get `target="_blank"` and `rel="noopener noreferrer"`.
- `null`/empty input returns `''`.

Existing `frontend/src/lib/chat.test.ts` is untouched.

## Non-goals (YAGNI)

- Syntax highlighting of code blocks.
- Copy-to-clipboard on code blocks.
- Rendering user-typed messages as markdown.
- Streaming-aware incremental/partial-markdown parsing (re-parsing the full
  accumulated string per token is fine at this scale).

## Verification

- `npm run test` (frontend) — new markdown tests pass, existing tests pass.
- `npm run check` — no type errors.
- `npm run lint` — passes.
- Manual: open the chat page, send a prompt that returns headings, a list,
  and a code block; confirm formatting renders during streaming and after
  the message finalizes; confirm user messages still show as plain text.
