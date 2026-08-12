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
    <div class="metrics">
      <div>
        <span class="muted small">Sessions</span><strong
          >{selected.computed.strengthening_sessions}</strong
        >
      </div>
      <div>
        <span class="muted small">Avg episodes/day</span><strong
          >{selected.computed.avg_pain_episodes_per_day ?? '—'}</strong
        >
      </div>
      <div>
        <span class="muted small">Avg tingling</span><strong
          >{selected.computed.avg_tingling_level ?? '—'}</strong
        >
      </div>
      <div>
        <span class="muted small">Worst pain</span><strong
          >{selected.computed.worst_pain ?? '—'}</strong
        >
      </div>
      <div>
        <span class="muted small">Days logged</span><strong>{selected.computed.days_logged}</strong>
      </div>
      <div>
        <span class="muted small">Sitting</span><strong
          >{Math.round(selected.computed.sitting_minutes / 60)}h</strong
        >
      </div>
    </div>
    <p class="muted small">
      G/A/R days: {selected.computed.green_days}/{selected.computed.amber_days}/{selected.computed
        .red_days} · suggested status <strong>{selected.computed.suggested_status}</strong>
    </p>

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
    <div class="field">
      <div class="fieldhead">
        <label>Key observations</label>
        {#if editObs && !editingObs}
          <button class="link" onclick={() => (editingObs = true)}>✎ Edit</button>
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
      {#if editObs && !editingObs}
        <!-- eslint-disable-next-line svelte/no-at-html-tags -- renderMarkdown sanitizes via DOMPurify -->
        <div class="markdown rendered">{@html renderMarkdown(editObs)}</div>
      {:else}
        <textarea bind:value={editObs} rows="6" placeholder="What stood out this week…"></textarea>
      {/if}
    </div>
    <div class="field">
      <div class="fieldhead">
        <label>Next steps</label>
        {#if editNext && !editingNext}
          <button class="link" onclick={() => (editingNext = true)}>✎ Edit</button>
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
      {#if editNext && !editingNext}
        <!-- eslint-disable-next-line svelte/no-at-html-tags -- renderMarkdown sanitizes via DOMPurify -->
        <div class="markdown rendered">{@html renderMarkdown(editNext)}</div>
      {:else}
        <textarea bind:value={editNext} rows="4" placeholder="Plan for the upcoming week…"
        ></textarea>
      {/if}
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
  .metrics {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 0.75rem;
    margin-bottom: 0.75rem;
  }
  .metrics div {
    display: flex;
    flex-direction: column;
  }
  .metrics strong {
    font-size: 1.2rem;
  }
  .opt {
    flex: 1;
    font-weight: 600;
  }

  @media (max-width: 640px) {
    .metrics {
      grid-template-columns: 1fr;
    }
  }
  .fieldhead {
    display: flex;
    align-items: center;
    justify-content: space-between;
  }
  .link {
    border: none;
    background: none;
    color: var(--text-muted);
    padding: 0;
    font-size: 0.85rem;
  }
  .rendered {
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 0.5rem 0.75rem;
    background: var(--surface-2);
  }
  .markdown :global(> :first-child) {
    margin-top: 0;
  }
  .markdown :global(> :last-child) {
    margin-bottom: 0;
  }
  .markdown :global(h1),
  .markdown :global(h2),
  .markdown :global(h3) {
    margin: 0.6rem 0 0.3rem;
    line-height: 1.25;
  }
  .markdown :global(p),
  .markdown :global(ul),
  .markdown :global(ol) {
    margin: 0.4rem 0;
  }
  .markdown :global(ul),
  .markdown :global(ol) {
    padding-left: 1.25rem;
  }
  .markdown :global(li) {
    margin: 0.15rem 0;
  }
</style>
