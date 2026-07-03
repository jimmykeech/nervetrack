<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import { TimerStore } from '$lib/stores/timer.svelte';
  import { TinglingTimerStore } from '$lib/stores/tingling.svelte';
  import {
    formatDuration,
    formatMinutesish,
    POSTURE_LABEL,
    POSTURES,
    sitStandRatio
  } from '$lib/time';
  import type { Posture } from '$lib/types';
  import RatioBar from '$lib/components/RatioBar.svelte';
  import { postureColor, POSTURE_META } from '$lib/posture';

  function postureColorVar(p: Posture): string {
    return POSTURE_META[p].cssVar;
  }

  const store = new TimerStore();
  const tingle = new TinglingTimerStore();
  const NUDGE_SECONDS = 45 * 60;

  let label = $state('');
  let tingleLevel = $state<number | null>(null);

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

  async function editTime(id: string, field: 'started_at' | 'ended_at', current: string | null) {
    const initial = current ? new Date(current + 'Z').toISOString().slice(0, 16) : '';
    const input = prompt(
      `New ${field === 'started_at' ? 'start' : 'end'} time (YYYY-MM-DDTHH:MM)`,
      initial
    );
    if (!input) return;
    const utc = new Date(input).toISOString().slice(0, 19);
    await store.editInterval(id, { [field]: utc });
  }

  const running = $derived(store.running);
  const totals = $derived(store.totals);
  const nudge = $derived(
    running ? store.elapsed >= NUDGE_SECONDS && running.posture === 'sitting' : false
  );
</script>

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
  <h3 style="margin-top: 0">Tingling timer</h3>
  <div class="card display" class:running={!!tingle.running} style="margin-bottom: 0.75rem">
    {#if tingle.running}
      <div class="posture">Tingling · level {tingle.running.level}</div>
      <div class="clock">{formatDuration(tingle.elapsed)}</div>
    {:else}
      <div class="posture muted">Not tracking</div>
      <div class="clock muted">00s</div>
    {/if}
  </div>
  <div class="row" style="align-items: flex-end; gap: 0.75rem">
    <div class="field" style="margin: 0; max-width: 10rem">
      <label>Tingling level (0–10)</label>
      <input type="number" min="0" max="10" step="0.5" bind:value={tingleLevel} />
    </div>
    <button
      class="btn-primary"
      onclick={startTingle}
      disabled={tingleLevel === null || !!tingle.running}>Start</button
    >
    <button onclick={stopTingle} disabled={!tingle.running}>Stop</button>
  </div>
  {#if tingle.intervals.length > 0}
    <div class="table-scroll" style="margin-top: 0.75rem">
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
  {/if}
</div>

<div class="card">
  <h3 style="margin-top: 0">Today's timeline</h3>
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
                ><button class="link" onclick={() => editTime(iv.id, 'started_at', iv.started_at)}
                  >{fmtTime(iv.started_at)}</button
                ></td
              >
              <td>
                {#if iv.ended_at}
                  <button class="link" onclick={() => editTime(iv.id, 'ended_at', iv.ended_at)}
                    >{fmtTime(iv.ended_at)}</button
                  >
                {:else}
                  <span class="live">running</span>
                {/if}
              </td>
              <td>{iv.duration_seconds != null ? formatMinutesish(iv.duration_seconds) : '—'}</td>
              <td
                ><button class="link danger" onclick={() => store.deleteInterval(iv.id)}
                  >delete</button
                ></td
              >
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
  {/if}
</div>

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

  @media (max-width: 640px) {
    .postures {
      grid-template-columns: 1fr;
    }
    .tgrid {
      grid-template-columns: repeat(2, 1fr);
    }
  }
</style>
