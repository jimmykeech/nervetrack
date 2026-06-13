<script lang="ts">
  import { onMount } from 'svelte';
  import { api } from '$lib/api';
  import type { Status, WeeklySummary } from '$lib/types';

  let weeks = $state<WeeklySummary[]>([]);
  let selected = $state<WeeklySummary | null>(null);
  let editStatus = $state<Status | null>(null);
  let editObs = $state('');
  let editTrend = $state('');
  let message = $state('');

  const trends = ['Better', 'Same', 'Slightly Worse', 'Worse'];
  const statusClass: Record<string, string> = { G: 'status-G', A: 'status-A', R: 'status-R' };

  async function load() {
    weeks = await api.listWeeks();
    if (weeks.length && !selected) select(weeks[0]);
  }
  onMount(load);

  function select(w: WeeklySummary) {
    selected = w;
    editStatus = w.overall_status ?? w.computed.suggested_status ?? null;
    editObs = w.key_observations ?? '';
    editTrend = w.trend_vs_last_week ?? '';
    message = '';
  }

  async function save() {
    if (!selected) return;
    const updated = await api.saveWeek(selected.week_start, {
      overall_status: editStatus ?? undefined,
      key_observations: editObs || undefined,
      trend_vs_last_week: editTrend || undefined
    });
    message = 'Saved ✓';
    weeks = weeks.map((w) => (w.week_start === updated.week_start ? updated : w));
    selected = updated;
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
    <h3 style="margin-top: 0">{selected.week_start} → {selected.week_end}</h3>
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
            onclick={() => (editStatus = s as Status)}>{s}</button
          >
        {/each}
      </div>
    </div>
    <div class="field">
      <label>Trend vs last week</label>
      <select bind:value={editTrend}>
        <option value="">—</option>
        {#each trends as t}<option value={t}>{t}</option>{/each}
      </select>
    </div>
    <div class="field">
      <label>Key observations</label>
      <textarea bind:value={editObs} rows="6" placeholder="What stood out this week…"></textarea>
    </div>
    <button class="status-G" onclick={save}>Save</button>
    {#if message}<span class="saved" style="margin-left: 0.75rem">{message}</span>{/if}
  </div>
{/if}

<style>
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
</style>
