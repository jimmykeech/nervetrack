<script lang="ts">
  import { onMount } from 'svelte';
  import { api } from '$lib/api';
  import LineChart from '$lib/components/LineChart.svelte';
  import { todayISO, utcNaiveToLocalInput } from '$lib/time';
  import type { Exercise, ExerciseLog, SessionDetail } from '$lib/types';
  import { activePainInstances } from '$lib/stores/painInstances.svelte';

  let exercises = $state<Exercise[]>([]);
  let date = $state(todayISO());
  let intensity = $state<number | null>(null);
  let sessionNotes = $state('');
  let rows = $state<Record<string, ExerciseLog>>({});
  let added = $state<string[]>([]);
  let lastLogs = $state<Record<string, Partial<ExerciseLog>>>({});
  let toAdd = $state('');
  let saved = $state<SessionDetail | null>(null);
  let message = $state('');
  let sessionInstanceIds = $state<string[]>([]);
  let loggedSessions = $state<SessionDetail[]>([]);
  let editingId = $state<string | null>(null);

  function toggleSessionInstance(id: string) {
    sessionInstanceIds = sessionInstanceIds.includes(id)
      ? sessionInstanceIds.filter((x) => x !== id)
      : [...sessionInstanceIds, id];
  }

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
    lastLogs = await api.lastLogs();
    // Fresh slate every time: no prefilled exercises, intensity, notes, or tags.
    rows = {};
    added = [];
    toAdd = '';
    intensity = null;
    sessionNotes = '';
    sessionInstanceIds = [];
  }

  onMount(load);

  async function loadSessions(d: string = date) {
    loggedSessions = await api.sessionsForDate(d);
  }

  $effect(() => {
    // Reading `date` inline registers it as a dependency: refetch on day change.
    loadSessions(date);
  });

  function sessionTime(s: SessionDetail): string {
    return utcNaiveToLocalInput(s.performed_at).slice(11, 16); // HH:MM, local
  }

  function sessionExercises(s: SessionDetail): string {
    return s.logs
      .map((l) => l.exercise_name)
      .filter(Boolean)
      .join(', ');
  }

  function isTimeBased(name: string): boolean {
    const n = name.toLowerCase();
    return n.includes('plank') || n.includes('hold');
  }

  function addExerciseToSession(id: string) {
    if (!id || added.includes(id)) return;
    rows[id] = { ...blankRow(id), ...(lastLogs[id] ?? {}) };
    added = [...added, id];
    toAdd = '';
  }

  function removeFromSession(id: string) {
    added = added.filter((x) => x !== id);
    delete rows[id];
  }

  function exerciseName(id: string): string {
    return exercises.find((e) => e.id === id)?.name ?? '';
  }

  const availableToAdd = $derived(exercises.filter((e) => !added.includes(e.id)));

  function editSession(s: SessionDetail) {
    editingId = s.id;
    added = s.logs.map((l) => l.exercise_id);
    rows = Object.fromEntries(
      s.logs.map((l) => [
        l.exercise_id,
        {
          exercise_id: l.exercise_id,
          sets: l.sets,
          reps: l.reps,
          hold_seconds: l.hold_seconds,
          weight_kg: l.weight_kg,
          difficulty: l.difficulty,
          nerve_response: l.nerve_response,
          modification: l.modification
        }
      ])
    );
    intensity = s.intensity;
    sessionNotes = s.notes ?? '';
    sessionInstanceIds = [...s.instance_ids];
    message = '';
  }

  function cancelEdit() {
    editingId = null;
    rows = {};
    added = [];
    intensity = null;
    sessionNotes = '';
    sessionInstanceIds = [];
    message = '';
  }

  async function removeSession(s: SessionDetail) {
    if (!confirm('Delete this logged session?')) return;
    await api.deleteSession(s.id);
    if (editingId === s.id) cancelEdit();
    await loadSessions();
  }

  async function saveSession() {
    const logs = added.map((id) => rows[id]);
    const payload = {
      intensity,
      notes: sessionNotes || null,
      logs,
      instance_ids: sessionInstanceIds
    };
    if (editingId) {
      saved = await api.updateSession(editingId, payload);
      message = `Updated session with ${saved.logs.length} exercises.`;
    } else {
      saved = await api.createSession(date, payload);
      message = `Saved session with ${saved.logs.length} exercises.`;
    }
    editingId = null;
    rows = {};
    added = [];
    intensity = null;
    sessionNotes = '';
    sessionInstanceIds = [];
    await loadSessions();
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

  function token(name: string): string {
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || '#888';
  }

  const progDatasets = $derived([
    {
      label: 'Difficulty',
      data: progData.map((p) => p.difficulty as number | null),
      borderColor: token('--caution'),
      backgroundColor: token('--caution'),
      tension: 0.25,
      spanGaps: true
    },
    {
      label: 'Weight (kg)',
      data: progData.map((p) => p.weight_kg as number | null),
      borderColor: token('--accent'),
      backgroundColor: token('--accent'),
      tension: 0.25,
      spanGaps: true
    }
  ]);
</script>

<div class="card">
  <div class="row session-meta">
    <div class="field">
      <label>Session date</label>
      <input type="date" bind:value={date} />
    </div>
    <div class="field f-intensity">
      <label>Intensity (1–10)</label>
      <input type="number" min="1" max="10" step="0.5" bind:value={intensity} />
    </div>
  </div>
</div>

{#if loggedSessions.length}
  <div class="card">
    <h3 style="margin-top: 0">Logged sessions</h3>
    {#each loggedSessions as s (s.id)}
      <div class="logged">
        <div class="logged-head">
          <span class="logged-when"
            >{sessionTime(s)}{#if s.intensity}
              · intensity {s.intensity}{/if}</span
          >
          <span class="logged-actions">
            <button class="link" onclick={() => editSession(s)}>Edit</button>
            <button class="link danger" onclick={() => removeSession(s)}>Delete</button>
          </span>
        </div>
        {#if sessionExercises(s)}<div class="muted small">{sessionExercises(s)}</div>{/if}
        {#if s.notes}<div class="muted small logged-notes">"{s.notes}"</div>{/if}
      </div>
    {/each}
  </div>
{/if}

<div class="card" class:editing={editingId}>
  <h3 style="margin-top: 0">
    {editingId ? 'Edit session' : 'Log session'}
    {#if editingId}<button class="link" onclick={cancelEdit} style="margin-left: 0.5rem"
        >Cancel edit</button
      >{/if}
  </h3>
  <p class="muted small">
    Add each exercise as you do it — inputs prefill from the last time you logged it.
  </p>
  {#if availableToAdd.length}
    <div class="row picker">
      <select bind:value={toAdd} style="flex: 1">
        <option value="">Choose an exercise…</option>
        {#each availableToAdd as e}<option value={e.id}>{e.name}</option>{/each}
      </select>
      <button onclick={() => addExerciseToSession(toAdd)} disabled={!toAdd}>+ Add</button>
    </div>
  {:else}
    <p class="muted small">All exercises added.</p>
  {/if}
  <div class="rows">
    {#each added as id (id)}
      {@const name = exerciseName(id)}
      <div class="exrow on">
        <div class="exhead">
          <span class="exname">{name}</span>
          <button class="link" onclick={() => removeFromSession(id)}>✕ remove</button>
        </div>
        <div class="inputs">
          <span><label>Sets</label><input type="number" bind:value={rows[id].sets} /></span>
          {#if isTimeBased(name)}
            <span
              ><label>Hold (s)</label><input
                type="number"
                bind:value={rows[id].hold_seconds}
              /></span
            >
          {:else}
            <span><label>Reps</label><input type="number" bind:value={rows[id].reps} /></span>
          {/if}
          <span
            ><label>Weight (kg)</label><input
              type="number"
              step="0.5"
              bind:value={rows[id].weight_kg}
            /></span
          >
          <span
            ><label>Difficulty</label><input
              type="number"
              min="1"
              max="10"
              step="0.5"
              bind:value={rows[id].difficulty}
            /></span
          >
          <span class="wide"
            ><label>Nerve response</label><input
              bind:value={rows[id].nerve_response}
              placeholder="e.g. slight twinge 2nd set"
            /></span
          >
          <span class="wide"
            ><label>Modification</label><input
              bind:value={rows[id].modification}
              placeholder="e.g. heel elevation"
            /></span
          >
        </div>
      </div>
    {/each}
  </div>
  <div class="field" style="margin-top: 0.75rem">
    <label>Session notes</label>
    <input bind:value={sessionNotes} />
  </div>
  {#if activePainInstances().length}
    <div class="field" style="margin-top: 0.75rem">
      <label>Tag pain instance(s) (optional)</label>
      <div class="chips">
        {#each activePainInstances() as pi (pi.id)}
          <button
            type="button"
            class="chip"
            class:on={sessionInstanceIds.includes(pi.id)}
            onclick={() => toggleSessionInstance(pi.id)}
          >
            {pi.name}
          </button>
        {/each}
      </div>
    </div>
  {/if}
  <button class="status-G" onclick={saveSession}
    >{editingId ? 'Update session' : 'Save session'}</button
  >
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
  .exhead {
    display: flex;
    align-items: center;
    justify-content: space-between;
  }
  .picker {
    margin-bottom: 0.75rem;
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
    color: var(--text-muted);
    padding: 0;
    font-size: 0.85rem;
  }
  .chips {
    display: flex;
    flex-wrap: wrap;
    gap: 0.4rem;
    margin-top: 0.4rem;
  }
  .chip {
    border: 1px solid var(--border);
    background: var(--surface);
    color: var(--text-muted);
    border-radius: 999px;
    padding: 0.3rem 0.7rem;
    font-size: 0.85rem;
  }
  .chip.on {
    border-color: var(--accent);
    color: var(--text);
  }
  .logged {
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 0.5rem 0.75rem;
    margin-bottom: 0.5rem;
  }
  .logged-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
  }
  .logged-when {
    font-weight: 600;
    color: var(--text);
  }
  .logged-actions {
    display: flex;
    gap: 0.75rem;
  }
  .logged-notes {
    font-style: italic;
  }
  .link.danger {
    color: var(--danger, #c0392b);
  }
  .card.editing {
    border: 1px solid var(--accent);
  }
  .session-meta {
    align-items: center;
    gap: 1rem;
  }
  .session-meta .field {
    margin: 0;
  }
  .f-intensity {
    max-width: 10rem;
  }
  @media (max-width: 640px) {
    .session-meta {
      flex-direction: column;
      align-items: stretch;
      gap: 0.25rem;
    }
    .session-meta .field {
      max-width: none;
    }
  }
</style>
