<script lang="ts">
  import { onMount } from 'svelte';
  import { api } from '$lib/api';
  import type { Status, WeeklySummary } from '$lib/types';
  import { renderMarkdown } from '$lib/markdown';

  let weeks = $state<WeeklySummary[]>([]);
  let selected = $state<WeeklySummary | null>(null);
  let editStatus = $state<Status | null>(null);
  let editObs = $state('');
  let editTrend = $state('');
  let editNext = $state('');
  let drafting = $state(false);
  let message = $state('');
  let editingObs = $state(false);
  let editingNext = $state(false);
  let saveState = $state<'idle' | 'saving' | 'saved' | 'error'>('idle');
  let saveError = $state('');

  const trends = ['Better', 'Same', 'Slightly Worse', 'Worse'];
  const statusClass: Record<string, string> = { G: 'status-G', A: 'status-A', R: 'status-R' };

  async function load() {
    weeks = await api.listWeeks();
    if (weeks.length && !selected) select(weeks[0]);
  }
  onMount(load);

  function select(w: WeeklySummary) {
    selected = w;
    // Not `?? w.computed.suggested_status` — with auto-save that would persist a
    // status the user never picked. The suggestion is shown as a hint instead.
    editStatus = w.overall_status ?? null;
    editObs = w.key_observations ?? '';
    editTrend = w.trend_vs_last_week ?? '';
    editNext = w.next_steps ?? '';
    editingObs = false;
    editingNext = false;
    saveState = 'idle';
    saveError = '';
    message = '';
  }

  async function save() {
    if (!selected) return;
    const target = selected.week_start;
    saveState = 'saving';
    saveError = '';
    try {
      // All four fields go every time: save_week is a full overwrite, so an
      // omitted field is persisted as NULL.
      const updated = await api.saveWeek(target, {
        overall_status: editStatus ?? undefined,
        key_observations: editObs || undefined,
        trend_vs_last_week: editTrend || undefined,
        next_steps: editNext || undefined
      });
      weeks = weeks.map((w) => (w.week_start === updated.week_start ? updated : w));
      // The user may have switched weeks while the request was in flight;
      // writing back then would clobber the newly selected week with this
      // one's data.
      if (selected?.week_start !== target) return;
      selected = updated;
      saveState = 'saved';
    } catch (e) {
      // Auto-save is the only persistence path now: a silent failure would
      // hang the indicator on "Saving…" and drop the edit without a word.
      if (selected?.week_start !== target) return;
      saveError = (e as Error).message;
      saveState = 'error';
    }
  }

  async function draftWithAi() {
    if (!selected) return;
    drafting = true;
    message = '';
    try {
      const d = await api.weeklyDraft(selected.week_start);
      editObs = d.key_observations;
      editNext = d.next_steps;
      editingObs = false;
      editingNext = false;
      void save();
    } catch (e) {
      message = (e as Error).message.startsWith('409')
        ? 'Configure a model in Settings first.'
        : (e as Error).message;
    } finally {
      drafting = false;
    }
  }
</script>

<div class="card">
  <h2 style="margin: 0 0 0.75rem">Weeks</h2>
  {#if weeks.length === 0}
    <p class="muted small">No weeks yet — log some daily entries first.</p>
  {:else}
    <div class="weeklist">
      {#each weeks as w}
        <button
          class="weekchip {selected?.week_start === w.week_start ? 'sel' : ''}"
          onclick={() => select(w)}
        >
          <span>{w.week_start} → {w.week_end}</span>
          {#if w.overall_status}<span class="pill {statusClass[w.overall_status]}"
              >{w.overall_status}</span
            >{/if}
          {#if w.trend_vs_last_week}<span class="pill">{w.trend_vs_last_week}</span>{/if}
        </button>
      {/each}
    </div>
  {/if}
</div>

{#if selected}
  <div class="card">
    <div class="weekhead">
      <h3>{selected.week_start} → {selected.week_end}</h3>
      <span class="save-ind">
        {#if saveState === 'saving'}<span class="saving">Saving…</span>
        {:else if saveState === 'saved'}<span class="saved">Saved ✓</span>
        {:else if saveState === 'error'}<span class="savefail" title={saveError}>Save failed</span
          >{/if}
      </span>
    </div>
    <div class="strip tnum">
      <span><strong>{selected.computed.strengthening_sessions}</strong> sessions</span>
      <span><strong>{selected.computed.avg_pain_episodes_per_day ?? '—'}</strong> episodes/day</span
      >
      <span><strong>{selected.computed.avg_tingling_level ?? '—'}</strong> tingling</span>
      <span><strong>{selected.computed.worst_pain ?? '—'}</strong> worst pain</span>
      <span><strong>{selected.computed.days_logged}</strong> days</span>
      <span><strong>{Math.round(selected.computed.sitting_minutes / 60)}h</strong> sitting</span>
      <span
        ><strong
          >{selected.computed.green_days}/{selected.computed.amber_days}/{selected.computed
            .red_days}</strong
        > G/A/R</span
      >
    </div>

    <div class="field">
      <label>Overall status</label>
      <div class="row">
        {#each ['G', 'A', 'R'] as s}
          <button
            class="opt {editStatus === s ? `status-${s}` : ''}"
            onclick={() => {
              editStatus = s as Status;
              void save();
            }}>{s}</button
          >
        {/each}
      </div>
    </div>
    <div class="field">
      <label>Trend vs last week</label>
      <select bind:value={editTrend} onchange={() => void save()}>
        <option value="">—</option>
        {#each trends as t}<option value={t}>{t}</option>{/each}
      </select>
    </div>
    <div class="field">
      <button class="draft" onclick={draftWithAi} disabled={drafting}>
        {drafting ? 'Drafting…' : '✨ Draft with AI'}
      </button>
      {#if message}<span class="muted small" style="margin-left: 0.75rem">{message}</span>{/if}
    </div>
    <div class="review">
      <section class="block">
        <div class="blockhead">
          <span class="label-caps">Key observations</span>
          {#if editObs && !editingObs}
            <button
              class="link"
              aria-label="Edit key observations"
              onclick={() => (editingObs = true)}>✎ Edit</button
            >
          {:else if editingObs}
            <button
              class="link"
              onclick={() => {
                editingObs = false;
                void save();
              }}>Done</button
            >
          {/if}
        </div>
        {#if editingObs}
          <textarea
            bind:value={editObs}
            rows="16"
            aria-label="Key observations markdown"
            placeholder="What stood out this week…"
          ></textarea>
        {:else if editObs}
          <!-- eslint-disable-next-line svelte/no-at-html-tags -- renderMarkdown sanitizes via DOMPurify -->
          <div class="markdown">{@html renderMarkdown(editObs)}</div>
        {:else}
          <p class="muted small empty">No review yet — ✨ Draft with AI, or ✎ to write one.</p>
        {/if}
      </section>

      <section class="block">
        <div class="blockhead">
          <span class="label-caps">Next steps</span>
          {#if editNext && !editingNext}
            <button class="link" aria-label="Edit next steps" onclick={() => (editingNext = true)}
              >✎ Edit</button
            >
          {:else if editingNext}
            <button
              class="link"
              onclick={() => {
                editingNext = false;
                void save();
              }}>Done</button
            >
          {/if}
        </div>
        {#if editingNext}
          <textarea
            bind:value={editNext}
            rows="8"
            aria-label="Next steps markdown"
            placeholder="Plan for the upcoming week…"
          ></textarea>
        {:else if editNext}
          <!-- eslint-disable-next-line svelte/no-at-html-tags -- renderMarkdown sanitizes via DOMPurify -->
          <div class="markdown">{@html renderMarkdown(editNext)}</div>
        {:else}
          <p class="muted small empty">
            Nothing planned yet — ✨ Draft with AI, or ✎ to write one.
          </p>
        {/if}
      </section>
    </div>
  </div>
{/if}

<style>
  .weekhead {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    flex-wrap: wrap;
    margin-bottom: 0.75rem;
  }
  .weekhead h3 {
    margin: 0;
  }
  .save-ind {
    margin-left: auto;
  }
  /* `.saved` and `.saving` are global in app.css; the failure state is not. */
  .savefail {
    font-size: 0.8rem;
    color: var(--bad);
  }
  .weeklist {
    display: flex;
    flex-direction: column;
    gap: 0.4rem;
  }
  .weekchip {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    justify-content: flex-start;
    text-align: left;
  }
  .weekchip.sel {
    border-color: var(--accent);
  }
  .opt {
    flex: 1;
    font-weight: 600;
  }
  .link {
    border: none;
    background: none;
    color: var(--text-muted);
    padding: 0;
    font-size: 0.85rem;
  }

  .strip {
    display: flex;
    flex-wrap: wrap;
    gap: 0.4rem 1.1rem;
    padding: 0.55rem 0.9rem;
    background: var(--surface-2);
    border-radius: var(--r-pill);
    margin-bottom: 1.1rem;
    font-size: 0.8rem;
    color: var(--text-muted);
  }
  .strip strong {
    color: var(--text);
    font-size: 0.95rem;
    margin-right: 0.2rem;
  }

  .review {
    max-width: 62ch;
  }
  .block + .block {
    border-top: 1px solid var(--border);
    margin-top: 1.25rem;
    padding-top: 1.25rem;
  }
  .blockhead {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 0.4rem;
  }
  .empty {
    margin: 0;
  }
  textarea {
    font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
    font-size: 0.85rem;
    line-height: 1.5;
  }

  .markdown {
    line-height: 1.7;
  }
  .markdown :global(> :first-child) {
    margin-top: 0;
  }
  .markdown :global(> :last-child) {
    margin-bottom: 0;
  }
  /* The AI writes `###`; h2/h4 are styled the same as a fallback in case the
     model picks a different level. */
  .markdown :global(h2),
  .markdown :global(h3),
  .markdown :global(h4) {
    font-family: var(--font-display);
    font-size: 0.72rem;
    font-weight: 700;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: var(--accent);
    margin: 1.4rem 0 0.4rem;
  }
  .markdown :global(p),
  .markdown :global(ul),
  .markdown :global(ol) {
    margin: 0 0 0.85rem;
  }
  .markdown :global(ul),
  .markdown :global(ol) {
    padding-left: 1.25rem;
  }
  .markdown :global(li) {
    margin: 0.25rem 0;
  }
  .markdown :global(strong) {
    color: var(--text);
  }
</style>
