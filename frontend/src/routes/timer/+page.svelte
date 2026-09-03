<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import { TimerStore } from '$lib/stores/timer.svelte';
  import { TinglingTimerStore } from '$lib/stores/tingling.svelte';
  import {
    formatDuration,
    formatMinutesish,
    POSTURE_LABEL,
    POSTURES,
    sitStandRatio,
    shiftISODate,
    todayISO,
    normalizeLabel,
    endsAfterStart,
    utcNaiveToLocalInput,
    localInputToUtcNaive
  } from '$lib/time';
  import type { Interval, Posture } from '$lib/types';
  import RatioBar from '$lib/components/RatioBar.svelte';
  import TimelineBar from '$lib/components/TimelineBar.svelte';
  import { postureColor, POSTURE_META } from '$lib/posture';

  function postureColorVar(p: Posture): string {
    return POSTURE_META[p].cssVar;
  }

  const store = new TimerStore();
  const tingle = new TinglingTimerStore();
  const NUDGE_SECONDS = 45 * 60;

  let label = $state('');
  let tingleLevel = $state<number | null>(null);
  let editErr = $state('');
  let timeEditErr = $state('');
  let editingInterval = $state<Interval | null>(null);
  let editingField = $state<'started_at' | 'ended_at'>('started_at');
  let editStart = $state('');
  let editEnd = $state('');
  let savingTime = $state(false);
  let timeDialog: HTMLDialogElement;
  let timeEditTrigger: HTMLButtonElement | null = null;
  const isToday = $derived(store.date === todayISO());

  onMount(() => {
    store.load();
    store.startTicking();
    tingle.load();
    tingle.startTicking();
  });
  onDestroy(() => {
    store.stopTicking();
    tingle.stopTicking();
  });

  async function loadDay(date: string) {
    await Promise.all([store.load(date), tingle.load(date)]);
  }

  async function pick(posture: Posture) {
    await store.switchTo(posture, label.trim() || undefined);
    label = '';
  }

  async function stop() {
    await store.stop();
    label = '';
  }

  async function startTingle() {
    if (tingleLevel === null) return;
    await tingle.start(tingleLevel);
  }
  async function stopTingle() {
    await tingle.stop();
  }

  function fmtTime(iso: string): string {
    return new Date(iso + 'Z').toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  }

  function openTimeEditor(
    interval: Interval,
    field: 'started_at' | 'ended_at',
    trigger: HTMLButtonElement
  ) {
    editErr = '';
    timeEditErr = '';
    editingInterval = interval;
    editingField = field;
    editStart = utcNaiveToLocalInput(interval.started_at);
    editEnd = interval.ended_at ? utcNaiveToLocalInput(interval.ended_at) : '';
    timeEditTrigger = trigger;
    timeDialog.showModal();
    queueMicrotask(() => {
      const inputId = field === 'started_at' ? 'interval-start' : 'interval-end';
      timeDialog.querySelector<HTMLInputElement>(`#${inputId}`)?.focus();
    });
  }

  function closeTimeEditor() {
    timeDialog.close();
  }

  function handleTimeDialogClose() {
    editingInterval = null;
    timeEditErr = '';
    timeEditTrigger?.focus();
    timeEditTrigger = null;
  }

  async function saveTime(event: SubmitEvent) {
    event.preventDefault();
    if (!editingInterval) return;

    const start = localInputToUtcNaive(editStart);
    const end = editingInterval.ended_at ? localInputToUtcNaive(editEnd) : null;
    if (end && !endsAfterStart(start, end)) {
      timeEditErr = 'End time must be after the start time.';
      return;
    }

    const changes: Partial<Interval> = {};
    if (editStart !== utcNaiveToLocalInput(editingInterval.started_at)) {
      changes.started_at = start;
    }
    if (
      editingInterval.ended_at &&
      end &&
      editEnd !== utcNaiveToLocalInput(editingInterval.ended_at)
    ) {
      changes.ended_at = end;
    }
    if (Object.keys(changes).length === 0) {
      timeDialog.close();
      return;
    }

    savingTime = true;
    timeEditErr = '';
    try {
      await store.editInterval(editingInterval.id, changes);
      timeDialog.close();
    } catch {
      timeEditErr = 'Could not save the change. Please try again.';
    } finally {
      savingTime = false;
    }
  }

  async function editLabel(id: string, current: string | null) {
    editErr = '';
    const input = prompt('Label for this interval (leave empty to clear)', current ?? '');
    if (input === null) return; // cancelled
    try {
      await store.editInterval(id, { label: normalizeLabel(input) });
    } catch {
      editErr = 'Could not save the label.';
    }
  }

  const running = $derived(store.running);
  const totals = $derived(store.totals);
  const nudge = $derived(
    running ? store.elapsed >= NUDGE_SECONDS && running.posture === 'sitting' : false
  );
</script>

<div class="datebar card">
  <button onclick={() => loadDay(shiftISODate(store.date, -1))} aria-label="previous day">‹</button>
  <div class="datepick">
    <input
      type="date"
      value={store.date}
      max={todayISO()}
      onchange={(e) => loadDay((e.currentTarget as HTMLInputElement).value)}
    />
    {#if !isToday}<button class="today" onclick={() => loadDay(todayISO())}>Today</button>{/if}
  </div>
  <button
    onclick={() => loadDay(shiftISODate(store.date, 1))}
    aria-label="next day"
    disabled={store.date >= todayISO()}>›</button
  >
</div>

{#if isToday}
  <div class="card display" class:running={!!running}>
    {#if running}
      <div class="posture">{POSTURE_LABEL[running.posture]}</div>
      <div class="clock" style="color:{postureColor(running.posture)}">
        {formatDuration(store.elapsed)}
      </div>
      {#if running.label}<div class="muted">{running.label}</div>{/if}
    {:else}
      <div class="posture muted">Not tracking</div>
      <div class="clock muted">00s</div>
    {/if}
    {#if tingle.running}
      <div class="tingle-divider"></div>
      <div class="tingle-line">
        <span class="tingle-tag">Tingling</span>
        <span class="tingle-clock">{formatDuration(tingle.elapsed)}</span>
        <span class="tingle-lvl">· level {tingle.running.level}</span>
      </div>
    {/if}
    {#if nudge}
      <div class="nudge">You've been sitting for 45+ minutes — consider a stand break.</div>
    {/if}
  </div>

  <div class="card">
    <label>Optional label for next interval</label>
    <input bind:value={label} placeholder="e.g. work, meeting" />
    <div class="postures">
      {#each POSTURES as p}
        <button
          class="pbtn {running?.posture === p ? 'active' : ''}"
          style="--pc:var({postureColorVar(p)})"
          onclick={() => pick(p)}
        >
          {POSTURE_LABEL[p]}
        </button>
      {/each}
      <button class="stop" onclick={stop} disabled={!running}>Stop</button>
    </div>

    <div class="tingle-controls">
      <div class="tingle-caption"><span class="tingle-dot"></span>Tingling timer</div>
      <div class="row" style="align-items: flex-end; gap: 0.75rem">
        <div class="field" style="margin: 0; max-width: 8rem">
          <label>Level (0–10)</label>
          <input type="number" min="0" max="10" step="0.5" bind:value={tingleLevel} />
        </div>
        <button
          class="btn-primary"
          onclick={startTingle}
          disabled={tingleLevel === null || !!tingle.running}>Start</button
        >
        <button onclick={stopTingle} disabled={!tingle.running}>Stop</button>
      </div>
    </div>
  </div>
{/if}

<div class="card">
  <TimelineBar
    intervals={store.intervals}
    tingling={tingle.intervals}
    date={store.date}
    now={store.now}
  />
</div>

<div class="card totals">
  <div class="tgrid">
    {#each POSTURES as p}
      <div class="tcell">
        <div class="tlabel">{POSTURE_LABEL[p]}</div>
        <div class="tval">{formatMinutesish(totals[p])}</div>
      </div>
    {/each}
  </div>
  <div class="ratio">Sit : Stand = <strong>{sitStandRatio(totals)}</strong></div>
  <div style="margin-top: 0.9rem"><RatioBar {totals} showHeader={false} /></div>
</div>

<div class="card">
  <h3 style="margin-top: 0">{isToday ? "Today's timeline" : `Timeline — ${store.date}`}</h3>
  {#if editErr}<p class="error small">{editErr}</p>{/if}
  {#if store.intervals.length === 0}
    <p class="muted small">No intervals yet. Tap a posture above to start.</p>
  {:else}
    <div class="table-scroll">
      <table>
        <thead>
          <tr><th>Posture</th><th>Start</th><th>End</th><th>Duration</th><th></th></tr>
        </thead>
        <tbody>
          {#each store.intervals as iv}
            <tr>
              <td>{POSTURE_LABEL[iv.posture]}{iv.label ? ` · ${iv.label}` : ''}</td>
              <td
                ><button
                  class="link"
                  aria-label={`Edit start time for ${POSTURE_LABEL[iv.posture]} interval`}
                  onclick={(event) =>
                    openTimeEditor(iv, 'started_at', event.currentTarget as HTMLButtonElement)}
                  >{fmtTime(iv.started_at)}</button
                ></td
              >
              <td>
                {#if iv.ended_at}
                  <button
                    class="link"
                    aria-label={`Edit end time for ${POSTURE_LABEL[iv.posture]} interval`}
                    onclick={(event) =>
                      openTimeEditor(iv, 'ended_at', event.currentTarget as HTMLButtonElement)}
                    >{fmtTime(iv.ended_at)}</button
                  >
                {:else}
                  <span class="live">running</span>
                {/if}
              </td>
              <td>{iv.duration_seconds != null ? formatMinutesish(iv.duration_seconds) : '—'}</td>
              <td>
                <button class="link" onclick={() => editLabel(iv.id, iv.label)}>label</button>
                <button class="link danger" onclick={() => store.deleteInterval(iv.id)}
                  >delete</button
                >
              </td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
  {/if}
</div>

<dialog
  class="time-dialog"
  bind:this={timeDialog}
  aria-labelledby="time-dialog-title"
  aria-describedby="time-dialog-description"
  onclose={handleTimeDialogClose}
>
  {#if editingInterval}
    <form onsubmit={saveTime}>
      <h2 id="time-dialog-title">Edit interval times</h2>
      <p id="time-dialog-description" class="muted small">
        Review the start and {editingInterval.ended_at ? 'end' : 'running'} time. The {editingField ===
        'started_at'
          ? 'start'
          : 'end'} time is selected.
      </p>
      <div class="field">
        <label for="interval-start">Start date and time</label>
        <input
          id="interval-start"
          type="datetime-local"
          step="60"
          bind:value={editStart}
          required
        />
      </div>
      {#if editingInterval.ended_at}
        <div class="field">
          <label for="interval-end">End date and time</label>
          <input id="interval-end" type="datetime-local" step="60" bind:value={editEnd} required />
        </div>
      {:else}
        <p class="muted small">This interval is still running, so it has no end time.</p>
      {/if}
      {#if timeEditErr}<p class="error small" role="alert">{timeEditErr}</p>{/if}
      <div class="dialog-actions">
        <button type="button" onclick={closeTimeEditor} disabled={savingTime}>Cancel</button>
        <button class="btn-primary" type="submit" disabled={savingTime}
          >{savingTime ? 'Saving…' : 'Save'}</button
        >
      </div>
    </form>
  {/if}
</dialog>

{#if tingle.intervals.length > 0}
  <div class="card">
    <h3 style="margin-top: 0">Tingling intervals</h3>
    <div class="table-scroll">
      <table>
        <thead>
          <tr><th>Level</th><th>Start</th><th>End</th><th>Duration</th><th></th></tr>
        </thead>
        <tbody>
          {#each tingle.intervals as iv}
            <tr>
              <td>{iv.level}</td>
              <td>{fmtTime(iv.started_at)}</td>
              <td>{iv.ended_at ? fmtTime(iv.ended_at) : 'running'}</td>
              <td>{iv.duration_seconds != null ? formatMinutesish(iv.duration_seconds) : '—'}</td>
              <td
                ><button class="link danger" onclick={() => tingle.remove(iv.id)}>delete</button
                ></td
              >
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
  </div>
{/if}

<style>
  .display {
    text-align: center;
    padding: 2rem 1rem;
  }
  .display.running {
    border-color: var(--accent);
  }
  .posture {
    font-size: 1.1rem;
    text-transform: uppercase;
    letter-spacing: 0.08em;
  }
  .clock {
    font-size: 3rem;
    font-weight: 700;
    font-variant-numeric: tabular-nums;
    margin: 0.25rem 0;
  }
  .nudge {
    margin-top: 0.75rem;
    color: var(--caution);
    font-weight: 600;
  }
  .tingle-divider {
    height: 1px;
    background: var(--border);
    width: 78%;
    margin: 0.95rem auto 0.8rem;
  }
  .tingle-line {
    display: flex;
    align-items: baseline;
    justify-content: center;
    gap: 0.5rem;
  }
  .tingle-tag {
    font-size: 0.78rem;
    text-transform: uppercase;
    letter-spacing: 0.07em;
    color: var(--tingle);
    font-weight: 700;
  }
  .tingle-clock {
    font-size: 1.5rem;
    font-weight: 650;
    font-variant-numeric: tabular-nums;
  }
  .tingle-lvl {
    font-size: 0.8rem;
    color: var(--text-muted);
  }
  .tingle-controls {
    margin-top: 1rem;
    padding-top: 0.95rem;
    border-top: 1px dashed var(--border);
  }
  .tingle-caption {
    display: inline-flex;
    align-items: center;
    gap: 0.4rem;
    font-size: 0.78rem;
    color: var(--text-muted);
    margin-bottom: 0.5rem;
  }
  .tingle-dot {
    width: 0.6rem;
    height: 0.6rem;
    border-radius: 50%;
    background: var(--tingle);
  }
  .postures {
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 0.6rem;
    margin-top: 0.75rem;
  }
  .pbtn {
    padding: 1rem;
    font-size: 1.05rem;
    font-weight: 600;
  }
  .pbtn.active {
    background: var(--pc);
    border-color: var(--pc);
    color: #1c130a;
  }
  .stop {
    grid-column: 1 / -1;
    padding: 0.9rem;
  }
  .tgrid {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 0.5rem;
    text-align: center;
  }
  .tlabel {
    color: var(--text-muted);
    font-size: 0.8rem;
  }
  .tval {
    font-size: 1.15rem;
    font-weight: 650;
    font-variant-numeric: tabular-nums;
  }
  .ratio {
    text-align: center;
    margin-top: 0.75rem;
    color: var(--text-muted);
  }
  .link {
    border: none;
    background: none;
    color: var(--accent);
    padding: 0;
    font-size: 0.9rem;
  }
  .link.danger {
    color: var(--bad);
  }
  .live {
    color: var(--good);
    font-size: 0.85rem;
  }

  .datebar {
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }
  .datepick {
    flex: 1;
    display: flex;
    gap: 0.5rem;
    align-items: center;
  }
  .error {
    color: var(--bad);
  }
  .time-dialog {
    width: min(30rem, calc(100% - 2rem));
    border: 1px solid var(--border);
    border-radius: var(--r-lg);
    padding: 1.25rem;
    background: var(--surface);
    color: var(--text);
    box-shadow: var(--shadow);
  }
  .time-dialog::backdrop {
    background: rgb(0 0 0 / 0.6);
  }
  .time-dialog h2 {
    margin: 0 0 0.5rem;
  }
  .time-dialog input[type='datetime-local'] {
    min-width: 0;
  }
  .time-dialog form > p:first-of-type {
    margin-top: 0;
  }
  .dialog-actions {
    display: flex;
    justify-content: flex-end;
    gap: 0.6rem;
    margin-top: 1rem;
  }

  @media (max-width: 640px) {
    .postures {
      grid-template-columns: 1fr;
    }
    .tgrid {
      grid-template-columns: repeat(2, 1fr);
    }
  }
</style>
