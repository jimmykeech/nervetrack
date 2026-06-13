<script lang="ts">
  import { page } from '$app/stores';
  import { api } from '$lib/api';
  import StatusToggle from '$lib/components/StatusToggle.svelte';
  import Stepper from '$lib/components/Stepper.svelte';
  import RatioBar from '$lib/components/RatioBar.svelte';
  import { formatMinutesLabel, parseDurationToMinutes, shiftISODate, todayISO } from '$lib/time';
  import type { DailyEntry, Status } from '$lib/types';

  let date = $state($page.url.searchParams.get('date') ?? todayISO());
  let entry = $state<DailyEntry | null>(null);
  let saveState = $state<'idle' | 'saving' | 'saved'>('idle');

  // Editable form fields.
  let status = $state<Status | null>(null);
  let strengthening_done = $state(false);
  let session_intensity = $state<number | null>(null);
  let worst_pain = $state<number | null>(null);
  let tingling_level = $state<number | null>(null);
  let tingling_text = $state('');
  let stretches_morning = $state(false);
  let stretches_night = $state(false);
  let iced = $state(false);
  let sleep_quality = $state<number | null>(null);
  let sitting_breaks = $state('');
  let notes = $state('');

  // Pain jab mini-form.
  let showJab = $state(false);
  let jabLevel = $state<number | null>(3);
  let jabContext = $state('');

  let saveTimer: ReturnType<typeof setTimeout> | null = null;
  let loadedKey = $state('');

  async function load(d: string) {
    entry = await api.getEntry(d);
    status = entry?.status ?? null;
    strengthening_done = entry?.strengthening_done ?? false;
    session_intensity = entry?.session_intensity ?? null;
    worst_pain = entry?.worst_pain ?? null;
    tingling_level = entry?.tingling_level ?? null;
    tingling_text = formatMinutesLabel(entry?.tingling_duration_minutes ?? null);
    stretches_morning = entry?.stretches_morning ?? false;
    stretches_night = entry?.stretches_night ?? false;
    iced = entry?.iced ?? false;
    sleep_quality = entry?.sleep_quality ?? null;
    sitting_breaks = entry?.sitting_breaks ?? '';
    notes = entry?.notes ?? '';
    loadedKey = d;
    saveState = 'idle';
  }

  $effect(() => {
    if (date !== loadedKey) load(date);
  });

  function scheduleSave() {
    if (loadedKey !== date) return; // don't save mid-load
    saveState = 'saving';
    if (saveTimer) clearTimeout(saveTimer);
    saveTimer = setTimeout(save, 700);
  }

  async function save() {
    const payload = {
      status,
      strengthening_done,
      session_intensity,
      worst_pain,
      tingling_level,
      tingling_duration_minutes: parseDurationToMinutes(tingling_text),
      stretches_morning,
      stretches_night,
      iced,
      sleep_quality,
      sitting_breaks: sitting_breaks || null,
      notes: notes || null
    };
    entry = await api.upsertEntry(date, payload as Partial<DailyEntry>);
    saveState = 'saved';
  }

  async function logJab() {
    await api.addPainEvent(date, {
      pain_level: jabLevel ?? undefined,
      context: jabContext || undefined
    });
    jabContext = '';
    showJab = false;
    await load(date);
  }

  async function removeJab(id: string) {
    await api.deletePainEvent(id);
    await load(date);
  }

  function fmtTime(iso: string): string {
    return new Date(iso + 'Z').toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  }

  const totals = $derived(entry?.timer_totals ?? { sitting: 0, standing: 0, lying: 0, walking: 0 });
  const isToday = $derived(date === todayISO());
</script>

<div class="datebar card">
  <button onclick={() => (date = shiftISODate(date, -1))} aria-label="previous day">‹</button>
  <div class="datepick">
    <input type="date" bind:value={date} />
    {#if !isToday}<button class="today" onclick={() => (date = todayISO())}>Today</button>{/if}
  </div>
  <button
    onclick={() => (date = shiftISODate(date, 1))}
    aria-label="next day"
    disabled={date >= todayISO()}>›</button
  >
  <span class="save-ind">
    {#if saveState === 'saving'}<span class="saving">Saving…</span>
    {:else if saveState === 'saved'}<span class="saved">Saved ✓</span>{/if}
  </span>
</div>

<div class="card">
  <label>Status</label>
  <StatusToggle bind:value={status} onChange={scheduleSave} />
</div>

<div class="card">
  <div class="grid-2">
    <div>
      <Stepper
        label="Worst pain (0–10)"
        bind:value={worst_pain}
        min={0}
        max={10}
        step={0.5}
        onChange={scheduleSave}
      />
    </div>
    <div>
      <Stepper
        label="Tingling level (0–10)"
        bind:value={tingling_level}
        min={0}
        max={10}
        step={0.5}
        onChange={scheduleSave}
      />
    </div>
    <div>
      <Stepper
        label="Sleep quality (1–5)"
        bind:value={sleep_quality}
        min={1}
        max={5}
        step={0.5}
        onChange={scheduleSave}
      />
    </div>
    <div>
      <label>Tingling duration</label>
      <input placeholder="e.g. 2hrs, 30min" bind:value={tingling_text} oninput={scheduleSave} />
    </div>
  </div>
</div>

<div class="card">
  <div class="checks">
    <label class="check"
      ><input type="checkbox" bind:checked={strengthening_done} onchange={scheduleSave} /> Strengthening
      session</label
    >
    <label class="check"
      ><input type="checkbox" bind:checked={stretches_morning} onchange={scheduleSave} /> Stretches —
      morning</label
    >
    <label class="check"
      ><input type="checkbox" bind:checked={stretches_night} onchange={scheduleSave} /> Stretches — night</label
    >
    <label class="check"
      ><input type="checkbox" bind:checked={iced} onchange={scheduleSave} /> Iced piriformis</label
    >
  </div>
  {#if strengthening_done}
    <div style="margin-top: 0.75rem; max-width: 16rem">
      <Stepper
        label="Session intensity (1–10)"
        bind:value={session_intensity}
        min={1}
        max={10}
        step={0.5}
        onChange={scheduleSave}
      />
    </div>
  {/if}
</div>

<div class="card">
  <div class="jab-head">
    <div>
      <div class="big">{entry?.sharp_pain_episodes ?? 0}</div>
      <div class="muted small">sharp pain episodes today</div>
    </div>
    <button class="status-R" onclick={() => (showJab = !showJab)}>＋ Log a pain jab</button>
  </div>
  {#if showJab}
    <div class="jab-form">
      <div style="flex: 1; min-width: 8rem">
        <Stepper label="Level" bind:value={jabLevel} min={0} max={10} step={0.5} />
      </div>
      <div style="flex: 2; min-width: 10rem">
        <label>Context (optional)</label>
        <input bind:value={jabContext} placeholder="e.g. sitting at desk" />
      </div>
      <button class="status-G" style="align-self: flex-end" onclick={logJab}>Log</button>
    </div>
  {/if}
  {#if entry?.pain_events?.length}
    <ul class="events">
      {#each entry.pain_events as ev}
        <li>
          <span
            >{fmtTime(ev.occurred_at)} · level {ev.pain_level ?? '—'}{ev.context
              ? ` · ${ev.context}`
              : ''}</span
          >
          <button class="link" onclick={() => removeJab(ev.id)}>remove</button>
        </li>
      {/each}
    </ul>
  {/if}
</div>

<div class="card">
  <label>Sitting breaks</label>
  <input bind:value={sitting_breaks} placeholder="e.g. Yes - many, A few" oninput={scheduleSave} />
</div>

<div class="card">
  <label>Notes</label>
  <textarea
    bind:value={notes}
    oninput={scheduleSave}
    placeholder="Pain events, activities, what helped…"
    rows="8"
  ></textarea>
</div>

<div class="card totals">
  <RatioBar {totals} />
  <a href="/timer" class="small">Open timer →</a>
</div>

<style>
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
  .datepick input {
    flex: 1;
  }
  .save-ind {
    min-width: 4rem;
    text-align: right;
  }
  .checks {
    display: flex;
    flex-direction: column;
    gap: 0.6rem;
  }
  .check {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    color: var(--text);
    font-size: 0.95rem;
    margin: 0;
  }
  .jab-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
  }
  .big {
    font-size: 1.8rem;
    font-weight: 700;
  }
  .jab-form {
    display: flex;
    gap: 0.75rem;
    flex-wrap: wrap;
    margin-top: 0.75rem;
  }
  .events {
    list-style: none;
    padding: 0;
    margin: 0.75rem 0 0;
  }
  .events li {
    display: flex;
    justify-content: space-between;
    padding: 0.35rem 0;
    border-bottom: 1px solid var(--border);
    font-size: 0.9rem;
  }
  .link {
    border: none;
    background: none;
    color: var(--muted);
    padding: 0;
    font-size: 0.85rem;
  }
  .totals a {
    display: inline-block;
    margin-top: 0.5rem;
  }
</style>
