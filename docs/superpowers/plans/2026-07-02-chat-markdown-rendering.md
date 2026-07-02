# Chat Markdown Rendering Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Render assistant (LLM) chat messages and the live streaming bubble as formatted, sanitized markdown instead of plain text.

**Architecture:** A pure, unit-tested helper (`renderMarkdown`) parses markdown with `marked` (GFM) and sanitizes the HTML with `DOMPurify`. The chat page inserts the result via Svelte's `{@html}` for assistant/streaming bubbles only; user messages stay plain text. Scoped CSS styles the rendered markdown inside assistant bubbles.

**Tech Stack:** SvelteKit (Svelte 5 runes), TypeScript, Vitest, `marked`, `dompurify`, `jsdom` (test only).

## Global Constraints

- Frontend lives in `frontend/`; run all `npm` commands from that directory.
- Vitest default environment is `node` (`frontend/vite.config.ts`); the markdown test must opt into jsdom with a `// @vitest-environment jsdom` file comment.
- Pure helpers live in `frontend/src/lib/` and stay UI-free (follow `frontend/src/lib/chat.ts`).
- LLM output is untrusted: HTML rendered via `{@html}` MUST be sanitized with DOMPurify. Non-negotiable.
- Only assistant/streaming content is rendered as markdown. User messages remain plain text.
- Theme CSS variables available: `--surface-2`, `--accent-soft`, `--accent` (used elsewhere in the app).

---

### Task 1: `renderMarkdown` helper, dependencies, and tests

**Files:**
- Modify: `frontend/package.json` (add deps)
- Create: `frontend/src/lib/markdown.ts`
- Test: `frontend/src/lib/markdown.test.ts`

**Interfaces:**
- Consumes: nothing (leaf module).
- Produces: `renderMarkdown(md: string | null): string` — returns sanitized HTML string; returns `''` for null/empty input. Anchors in the output carry `target="_blank"` and `rel="noopener noreferrer"`.

- [ ] **Step 1: Install dependencies**

Run from `frontend/`:

```bash
npm install marked dompurify
npm install -D jsdom
```

Expected: `marked` and `dompurify` appear under `dependencies` in `frontend/package.json`; `jsdom` under `devDependencies`. `npm install` exits 0.

- [ ] **Step 2: Write the failing test**

Create `frontend/src/lib/markdown.test.ts`:

```ts
// @vitest-environment jsdom
import { describe, expect, it } from 'vitest';
import { renderMarkdown } from './markdown';

describe('renderMarkdown', () => {
  it('returns empty string for null or empty input', () => {
    expect(renderMarkdown(null)).toBe('');
    expect(renderMarkdown('')).toBe('');
  });

  it('renders headings', () => {
    expect(renderMarkdown('## Hello')).toContain('<h2');
  });

  it('renders bold', () => {
    expect(renderMarkdown('**x**')).toContain('<strong>');
  });

  it('renders unordered lists', () => {
    const html = renderMarkdown('- a\n- b');
    expect(html).toContain('<ul>');
    expect((html.match(/<li>/g) ?? []).length).toBe(2);
  });

  it('renders fenced code blocks', () => {
    const html = renderMarkdown('```js\nconst a = 1;\n```');
    expect(html).toContain('<pre><code');
  });

  it('strips script tags (sanitization)', () => {
    const html = renderMarkdown('hello <script>alert(1)</script> world');
    expect(html).not.toContain('<script');
    expect(html).not.toContain('alert(1)');
  });

  it('strips javascript: links (sanitization)', () => {
    const html = renderMarkdown('[click](javascript:alert(1))');
    expect(html).not.toContain('javascript:');
  });

  it('opens links safely in a new tab', () => {
    const html = renderMarkdown('[docs](https://example.com)');
    expect(html).toContain('target="_blank"');
    expect(html).toContain('rel="noopener noreferrer"');
  });
});
```

- [ ] **Step 3: Run test to verify it fails**

Run from `frontend/`:

```bash
npm run test -- src/lib/markdown.test.ts
```

Expected: FAIL — module `./markdown` cannot be resolved / `renderMarkdown` is not defined.

- [ ] **Step 4: Write the implementation**

Create `frontend/src/lib/markdown.ts`:

```ts
// Parse markdown to sanitized HTML for rendering LLM output in the chat UI.
// Pure and UI-free so it is unit-testable (see markdown.test.ts). LLM output
// is untrusted, so the marked-produced HTML is always run through DOMPurify.
import DOMPurify from 'dompurify';
import { marked } from 'marked';

marked.setOptions({ gfm: true, breaks: true });

// Force links to open in a new tab and drop the opener reference.
DOMPurify.addHook('afterSanitizeAttributes', (node) => {
  if (node.tagName === 'A') {
    node.setAttribute('target', '_blank');
    node.setAttribute('rel', 'noopener noreferrer');
  }
});

export function renderMarkdown(md: string | null): string {
  if (!md) return '';
  const rawHtml = marked.parse(md, { async: false }) as string;
  return DOMPurify.sanitize(rawHtml);
}
```

- [ ] **Step 5: Run test to verify it passes**

Run from `frontend/`:

```bash
npm run test -- src/lib/markdown.test.ts
```

Expected: PASS (8 assertions across the described cases).

- [ ] **Step 6: Verify types and lint**

Run from `frontend/`:

```bash
npm run check
npm run lint
```

Expected: both exit 0.

- [ ] **Step 7: Commit**

```bash
git add frontend/package.json frontend/package-lock.json frontend/src/lib/markdown.ts frontend/src/lib/markdown.test.ts
git commit -m "feat(chat): add sanitized markdown render helper"
```

---

### Task 2: Render markdown in the chat page + styling

**Files:**
- Modify: `frontend/src/routes/chat/+page.svelte`

**Interfaces:**
- Consumes: `renderMarkdown(md: string | null): string` from `$lib/markdown` (Task 1).
- Produces: nothing (leaf UI change).

- [ ] **Step 1: Import the helper**

In `frontend/src/routes/chat/+page.svelte`, add the import inside the existing `<script lang="ts">` block, after the `ChatStore` import:

```ts
  import { renderMarkdown } from '$lib/markdown';
```

- [ ] **Step 2: Render assistant messages as markdown, keep user messages plain**

Replace the message-loop block (currently):

```svelte
      {#each chat.messages as m}
        <div class="msg {m.role}">
          <div class="bubble">{m.content}</div>
        </div>
      {/each}
```

with:

```svelte
      {#each chat.messages as m}
        <div class="msg {m.role}">
          {#if m.role === 'assistant'}
            <div class="bubble markdown">{@html renderMarkdown(m.content)}</div>
          {:else}
            <div class="bubble">{m.content}</div>
          {/if}
        </div>
      {/each}
```

- [ ] **Step 3: Render the live streaming bubble as markdown**

Replace (currently):

```svelte
      {#if chat.streaming}
        <div class="msg assistant"><div class="bubble">{chat.streaming}</div></div>
      {/if}
```

with:

```svelte
      {#if chat.streaming}
        <div class="msg assistant">
          <div class="bubble markdown">{@html renderMarkdown(chat.streaming)}</div>
        </div>
      {/if}
```

- [ ] **Step 4: Scope `pre-wrap` to non-markdown bubbles and add markdown styles**

In the `<style>` block, change the `.bubble` rule so `white-space: pre-wrap` no longer applies to markdown bubbles. Replace:

```css
  .bubble {
    max-width: 80%;
    padding: 0.5rem 0.75rem;
    border-radius: 0.75rem;
    white-space: pre-wrap;
  }
```

with:

```css
  .bubble {
    max-width: 80%;
    padding: 0.5rem 0.75rem;
    border-radius: 0.75rem;
  }
  .bubble:not(.markdown) {
    white-space: pre-wrap;
  }
```

Then add these markdown styles at the end of the `<style>` block (before the closing `</style>`):

```css
  .bubble.markdown :global(> :first-child) {
    margin-top: 0;
  }
  .bubble.markdown :global(> :last-child) {
    margin-bottom: 0;
  }
  .bubble.markdown :global(h1),
  .bubble.markdown :global(h2),
  .bubble.markdown :global(h3) {
    margin: 0.6rem 0 0.3rem;
    line-height: 1.25;
  }
  .bubble.markdown :global(p),
  .bubble.markdown :global(ul),
  .bubble.markdown :global(ol) {
    margin: 0.4rem 0;
  }
  .bubble.markdown :global(ul),
  .bubble.markdown :global(ol) {
    padding-left: 1.25rem;
  }
  .bubble.markdown :global(li) {
    margin: 0.15rem 0;
  }
  .bubble.markdown :global(code) {
    font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
    font-size: 0.9em;
    background: var(--surface-2);
    padding: 0.1em 0.3em;
    border-radius: 0.3rem;
  }
  .bubble.markdown :global(pre) {
    background: var(--surface-2);
    padding: 0.6rem 0.75rem;
    border-radius: 0.5rem;
    overflow-x: auto;
  }
  .bubble.markdown :global(pre code) {
    background: none;
    padding: 0;
  }
  .bubble.markdown :global(table) {
    border-collapse: collapse;
    margin: 0.4rem 0;
  }
  .bubble.markdown :global(th),
  .bubble.markdown :global(td) {
    border: 1px solid var(--surface-2);
    padding: 0.25rem 0.5rem;
  }
  .bubble.markdown :global(blockquote) {
    margin: 0.4rem 0;
    padding-left: 0.75rem;
    border-left: 3px solid var(--accent-soft);
    opacity: 0.9;
  }
  .bubble.markdown :global(a) {
    color: var(--accent);
    text-decoration: underline;
  }
```

Note: `:global(...)` is required because the markdown HTML is injected at runtime via `{@html}`, so Svelte's scoped-CSS compiler cannot see those elements to add scoping hashes.

- [ ] **Step 5: Verify types and lint**

Run from `frontend/`:

```bash
npm run check
npm run lint
```

Expected: both exit 0. (`{@html}` on sanitized content is expected; no svelte-check errors.)

- [ ] **Step 6: Run the full test suite**

Run from `frontend/`:

```bash
npm run test
```

Expected: all tests pass (existing `chat.test.ts` plus new `markdown.test.ts`).

- [ ] **Step 7: Manual verification**

Start the app (`npm run dev` from `frontend/`, with the backend running), open the chat page, and send a prompt that elicits structure, e.g. "Give me a heading, a bulleted list of 3 items, and a short JS code block."

Confirm:
- Headings, bullets, and the code block render formatted (not literal `##`/`-`/backticks).
- Formatting updates live while the response streams.
- The finalized assistant message keeps its formatting.
- A user message with characters like `**test**` still displays as plain text.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/routes/chat/+page.svelte
git commit -m "feat(chat): render assistant messages as markdown"
```

---

## Self-Review

**Spec coverage:**
- Pure helper `renderMarkdown` (spec §1) → Task 1.
- Component render sites: assistant + streaming markdown, user plain (spec §2) → Task 2 steps 1–3.
- Styling (spec §3) → Task 2 step 4.
- Dependencies marked/dompurify/jsdom (spec §4) → Task 1 step 1.
- Tests incl. sanitization + safe links (spec §5) → Task 1 step 2.
- Verification (spec) → Task 1 steps 5–6, Task 2 steps 5–7.
- Non-goals respected: no syntax highlighting, no copy button, no user-message markdown, no incremental parser.

**Placeholder scan:** No TBD/TODO; all code and commands are concrete.

**Type consistency:** `renderMarkdown(md: string | null): string` is defined identically in Task 1 (produces) and consumed in Task 2 (`m.content` is `string | null` per `ChatMessage`, `chat.streaming` is `string`). Class name `markdown` on the bubble matches between the template (steps 2–3) and CSS (step 4).
