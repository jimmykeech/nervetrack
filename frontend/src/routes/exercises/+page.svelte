<script lang="ts">
  import { onMount } from 'svelte';
  import { api } from '$lib/api';
  import LineChart from '$lib/components/LineChart.svelte';
  import { todayISO } from '$lib/time';
  import type { Exercise, ExerciseLog, SessionDetail } from '$lib/types';

  let exercises = $state<Exercise[]>([]);
  let date = $state(todayISO());
  let intensity = $state<number | null>(null);
  let sessionNotes = $state('');
  let rows = $state<Record<string, ExerciseLog>>({});
  let included = $state<Record<string, boolean>>({});
  let saved = $state<SessionDetail | null>(null);
  let message = $state('');

  let newExercise = $state('');

  // Progression view.
  let progExercise = $state<string>('');
  let progData = $state<Record<string, unknown>[]>([]);

  function blankRow(id: string): ExerciseLog {
    return {
      exercise_id: id,
      sets: null,
      reps: null,
      hold_seconds: null,
      weight_kg: null,
      difficulty: null,
      nerve_response: null,
      modification: null
    };
  }

  async function load() {
    exercises = (await api.listExercises()).filter((e) => e.active);
    const fresh: Record<string, ExerciseLog> = {};
    for (const e of exercises) fresh[e.id] = blankRow(e.id);
    rows = fresh;
    // Prefill from the most recent session ("same as last time" workflow).
    const last = await api.latestSession();
    if (last) {
      intensity = last.intensity;
      for (const log of last.logs) {
        if (rows[log.exercise_id]) {
          rows[log.exercise_id] = { ...log, id: undefined };
          included[log.exercise_id] = true;
        }
      }
    }
  }

  onMount(load);

  function isTimeBased(name: string): boolean {
    const n = name.toLowerCase();
    return n.includes('plank') || n.includes('hold');
  }

  async function saveSession() {
    const logs = exercises.filter((e) => included[e.id]).map((e) => rows[e.id]);
    saved = await api.createSession(date, { intensity, notes: sessionNotes || null, logs });
    message = `Saved session with ${saved.logs.length} exercises.`;
  }

  async function addExercise() {
    if (!newExercise.trim()) return;
    await api.createExercise(newExercise.trim());
    newExercise = '';
    await load();
  }

  async function deactivate(e: Exercise) {
    await api.patchExercise(e.id, { active: false });
    await load();
  }

  async function loadProgression() {
    if (!progExercise) return;
    progData = await api.progression(progExercise);
  }

  const progLabels = $derived(progData.map((p) => String(p.performed_at).slice(0, 10)));
  const progDatasets = $derived([
    {
      label: 'Difficulty',
      data: progData.map((p) => p.difficulty as number | null),
      borderColor: '#f5a623',
      backgroundColor: '#f5a623',
      tension: 0.25,
      spanGaps: true
    },
    {
      label: 'Weight (kg)',
      data: progData.map((p) => p.weight_kg as number | null),
      borderColor: '#4f8cff',
      backgroundColor: '#4f8cff',
      tension: 0.25,
      spanGaps: true
    }
  ]);
</script>

<div class="card">
  <div class="row" style="align-items: center; gap: 1rem">
    <div class="field" style="margin: 0">
      <label>Session date</label>
      <input type="date" bind:value={date} />
    </div>
    <div class="field" style="margin: 0; max-width: 10rem">
      <label>Intensity (1–10)</label>
      <input type="number" min="1" max="10" step="0.5" bind:value={intensity} />
    </div>
  </div>
</div>

<div class="card">
  <h3 style="margin-top: 0">Log session</h3>
  <p class="muted small">Prefilled from your last session. Tick the exercises you did.</p>
  <div class="rows">
    {#each exercises as e}
      <div class="exrow" class:on={included[e.id]}>
        <label class="exname">
          <input type="checkbox" bind:checked={included[e.id]} />
          {e.name}
        </label>
        {#if included[e.id]}
          <div class="inputs">
            <span><label>Sets</label><input type="number" bind:value={rows[e.id].sets} /></span>
            {#if isTimeBased(e.name)}
              <span
                ><label>Hold (s)</label><input
                  type="number"
                  bind:value={rows[e.id].hold_seconds}
                /></span
              >
            {:else}
              <span><label>Reps</label><input type="number" bind:value={rows[e.id].reps} /></span>
            {/if}
            <span
              ><label>Weight (kg)</label><input
                type="number"
                step="0.5"
                bind:value={rows[e.id].weight_kg}
              /></span
            >
            <span
              ><label>Difficulty</label><input
                type="number"
                min="1"
                max="10"
                step="0.5"
                bind:value={rows[e.id].difficulty}
              /></span
            >
            <span class="wide"
              ><label>Nerve response</label><input
                bind:value={rows[e.id].nerve_response}
                placeholder="e.g. slight twinge 2nd set"
              /></span
            >
            <span class="wide"
              ><label>Modification</label><input
                bind:value={rows[e.id].modification}
                placeholder="e.g. heel elevation"
              /></span
            >
          </div>
        {/if}
      </div>
    {/each}
  </div>
  <div class="field" style="margin-top: 0.75rem">
    <label>Session notes</label>
    <input bind:value={sessionNotes} />
  </div>
  <button class="status-G" onclick={saveSession}>Save session</button>
  {#if message}<span class="saved" style="margin-left: 0.75rem">{message}</span>{/if}
</div>

<div class="card">
  <h3 style="margin-top: 0">Catalogue</h3>
  <div class="row" style="margin-bottom: 0.75rem">
    <input bind:value={newExercise} placeholder="Add new exercise" style="flex: 1" />
    <button onclick={addExercise}>Add</button>
  </div>
  <ul class="cat">
    {#each exercises as e}
      <li>{e.name}<button class="link" onclick={() => deactivate(e)}>retire</button></li>
    {/each}
  </ul>
</div>

<div class="card">
  <h3 style="margin-top: 0">Progression</h3>
  <div class="row">
    <select bind:value={progExercise} onchange={loadProgression} style="flex: 1">
      <option value="">Choose an exercise…</option>
      {#each exercises as e}<option value={e.id}>{e.name}</option>{/each}
    </select>
  </div>
  {#if progData.length > 0}
    <div style="margin-top: 1rem"><LineChart labels={progLabels} datasets={progDatasets} /></div>
  {:else if progExercise}
    <p class="muted small">No history yet for this exercise.</p>
  {/if}
</div>

<style>
  .exrow {
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 0.6rem 0.75rem;
    margin-bottom: 0.5rem;
  }
  .exrow.on {
    border-color: var(--accent);
  }
  .exname {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    color: var(--text);
    font-weight: 600;
    margin: 0;
  }
  .inputs {
    display: flex;
    flex-wrap: wrap;
    gap: 0.5rem;
    margin-top: 0.6rem;
  }
  .inputs span {
    flex: 1 1 4.5rem;
  }
  .inputs span.wide {
    flex: 1 1 12rem;
  }
  .inputs input {
    width: 100%;
  }
  .cat {
    list-style: none;
    padding: 0;
    margin: 0;
  }
  .cat li {
    display: flex;
    justify-content: space-between;
    padding: 0.4rem 0;
    border-bottom: 1px solid var(--border);
  }
  .link {
    border: none;
    background: none;
    color: var(--muted);
    padding: 0;
    font-size: 0.85rem;
  }
</style>
