<script lang="ts">
  import { onMount } from 'svelte';
  import { page } from '$app/stores';
  import { api } from '$lib/api';
  import LineChart from '$lib/components/LineChart.svelte';
  import WorkoutEditor from '$lib/components/WorkoutEditor.svelte';
  import { todayISO, utcNaiveToLocalInput } from '$lib/time';
  import type { Exercise, ExerciseLog, SessionDetail, Workout, WorkoutIn } from '$lib/types';
  import {
    invalidSupersetGroups,
    nextSupersetGroup,
    supersetGroups,
    workoutExercises,
    workoutLogs
  } from '$lib/workouts';
  import { activePainInstances } from '$lib/stores/painInstances.svelte';

  let exercises = $state<Exercise[]>([]);
  let date = $state($page.url.searchParams.get('date') ?? todayISO());
  let intensity = $state<number | null>(null);
  let sessionNotes = $state('');
  let rows = $state<Record<string, ExerciseLog>>({});
  let added = $state<string[]>([]);
  let toAdd = $state('');
  let saved = $state<SessionDetail | null>(null);
  let message = $state('');
  let sessionInstanceIds = $state<string[]>([]);
  let loggedSessions = $state<SessionDetail[]>([]);
  let editingId = $state<string | null>(null);
  let workouts = $state<Workout[]>([]);
  let selectedWorkoutId = $state('');
  let sourceWorkoutName = $state('');
  let workoutDraft = $state<{ id: string | null; data: WorkoutIn; populate: boolean } | null>(null);
  let busy = $state(false);
  let error = $state('');
  const selectedWorkout = $derived(workouts.find((w) => w.id === selectedWorkoutId));
  const sessionLogs = $derived(added.map((id) => rows[id]));
  const invalidGroups = $derived(invalidSupersetGroups(sessionLogs));

  function createWorkout(logs: ExerciseLog[] = [], populate = true) {
    workoutDraft = { id: null, data: { name: '', exercises: workoutExercises(logs) }, populate };
  }

  function populateWorkout(workout: Workout) {
    cancelEdit();
    const logs = workoutLogs(workout.exercises);
    added = logs.map((log) => log.exercise_id);
    rows = Object.fromEntries(logs.map((log) => [log.exercise_id, log]));
    selectedWorkoutId = workout.id;
    sourceWorkoutName = workout.name;
  }

  function workoutSaved(workout: Workout) {
    const populate = workoutDraft?.populate;
    workouts = [...workouts.filter((w) => w.id !== workout.id), workout].sort((a, b) =>
      a.name.localeCompare(b.name)
    );
    workoutDraft = null;
    if (populate) populateWorkout(workout);
    message = `Saved workout “${workout.name}”. Your session is ready to review and save.`;
  }

  async function removeWorkout(workout: Workout) {
    if (!confirm(`Delete saved workout “${workout.name}”? Logged sessions will be kept.`)) return;
    busy = true;
    error = '';
    try {
      await api.deleteWorkout(workout.id);
      workouts = workouts.filter((w) => w.id !== workout.id);
      selectedWorkoutId = '';
    } catch (e) {
      error = e instanceof Error ? e.message : 'Could not delete workout.';
    } finally {
      busy = false;
    }
  }

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
      modification: null,
      superset_group: null
    };
  }

  async function load() {
    try {
      [exercises, workouts] = await Promise.all([api.listExercises(), api.listWorkouts()]);
    } catch (e) {
      error = e instanceof Error ? e.message : 'Could not load workouts.';
    }
  }

  onMount(load);

  async function loadSessions(d: string = date) {
    try {
      const sessions = await api.sessionsForDate(d);
      if (d === date) loggedSessions = sessions;
    } catch (e) {
      error = e instanceof Error ? e.message : 'Could not load sessions.';
    }
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

  function addExerciseToSession(id: string) {
    if (!id || added.includes(id)) return;
    rows[id] = blankRow(id);
    added = [...added, id];
    toAdd = '';
  }

  function removeFromSession(id: string) {
    added = added.filter((x) => x !== id);
    delete rows[id];
  }

  function exerciseName(id: string): string {
    return exercises.find((e) => e.id === id)?.name ?? rows[id]?.exercise_name ?? '';
  }

  const availableToAdd = $derived(exercises.filter((e) => e.active && !added.includes(e.id)));

  function editSession(s: SessionDetail) {
    workoutDraft = null;
    sourceWorkoutName = '';
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
          modification: l.modification,
          superset_group: l.superset_group
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
    error = '';
    toAdd = '';
    sourceWorkoutName = '';
  }

  async function removeSession(s: SessionDetail) {
    if (!confirm('Delete this logged session?')) return;
    await api.deleteSession(s.id);
    if (editingId === s.id) cancelEdit();
    await loadSessions();
  }

  async function saveSession() {
    if (busy || (!added.length && !editingId) || invalidGroups.length) return;
    busy = true;
    error = '';
    try {
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
      sourceWorkoutName = '';
      toAdd = '';
      await loadSessions();
    } catch (e) {
      error = e instanceof Error ? e.message : 'Could not save session.';
    } finally {
      busy = false;
    }
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
      <input type="date" bind:value={date} onchange={cancelEdit} disabled={busy} />
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
            <button
              class="link"
              onclick={() => createWorkout(s.logs)}
              disabled={busy || !!workoutDraft}>Save as workout</button
            >
            <button class="link" onclick={() => editSession(s)} disabled={busy || !!workoutDraft}
              >Edit</button
            >
            <button
              class="link danger"
              onclick={() => removeSession(s)}
              disabled={busy || !!workoutDraft}>Delete</button
            >
          </span>
        </div>
        {#if sessionExercises(s)}<div class="muted small">{sessionExercises(s)}</div>{/if}
        {#if s.notes}<div class="muted small logged-notes">"{s.notes}"</div>{/if}
      </div>
    {/each}
  </div>
{/if}

<div class="card">
  <h3 style="margin-top: 0">Saved workouts</h3>
  <p class="muted small">
    Choose a workout to fill a new session, or create and save a workout first.
  </p>
  <fieldset disabled={busy || !!workoutDraft}>
    {#if workouts.length}
      <div class="row picker">
        <select aria-label="Saved workout" bind:value={selectedWorkoutId} style="flex: 1">
          <option value="">Choose a workout…</option>
          {#each workouts as workout (workout.id)}
            <option value={workout.id}>{workout.name} ({workout.exercises.length} exercises)</option
            >
          {/each}
        </select>
        <button
          onclick={() => selectedWorkout && populateWorkout(selectedWorkout)}
          disabled={!selectedWorkout}>Use saved workout</button
        >
      </div>
      {#if selectedWorkout}
        <p class="muted small">
          {selectedWorkout.exercises.map((e) => e.exercise_name).join(', ')}
        </p>
      {/if}
    {:else}
      <p class="muted small">No saved workouts yet.</p>
    {/if}
    <div class="row">
      <button onclick={() => createWorkout()}>Create workout</button>
      {#if selectedWorkout}
        <button
          class="link"
          onclick={() => {
            if (selectedWorkout)
              workoutDraft = { id: selectedWorkout.id, data: selectedWorkout, populate: true };
          }}>Edit workout</button
        >
        <button
          class="link danger"
          onclick={() => selectedWorkout && removeWorkout(selectedWorkout)}>Delete workout</button
        >
      {/if}
    </div>
  </fieldset>
</div>

{#if workoutDraft}
  {#key workoutDraft}
    <WorkoutEditor
      {exercises}
      initial={workoutDraft.data}
      workoutId={workoutDraft.id}
      useAfterSave={workoutDraft.populate}
      onSave={workoutSaved}
      onCancel={() => (workoutDraft = null)}
    />
  {/key}
{/if}

{#if error}<p role="alert">{error}</p>{/if}
{#if message}<p class="saved" role="status">{message}</p>{/if}

{#if added.length || editingId || sourceWorkoutName}
  <div class="card" class:editing={editingId}>
    <fieldset disabled={busy || !!workoutDraft}>
      <h3 style="margin-top: 0">
        {editingId ? 'Edit session' : 'Log session'}
        {#if editingId}<button class="link" onclick={cancelEdit} style="margin-left: 0.5rem"
            >Cancel edit</button
          >{/if}
      </h3>
      <p class="muted small">
        {sourceWorkoutName ? `Workout: ${sourceWorkoutName}. ` : ''}Review the exercises and record
        this session’s results.
      </p>
      <details>
        <summary>Customize this session</summary>
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
      </details>
      <div class="rows">
        {#each added as id (id)}
          {@const name = exerciseName(id)}
          <div class="exrow on" class:superset={rows[id].superset_group !== null}>
            <div class="exhead">
              <span class="exname">
                {name}
                {#if rows[id].superset_group !== null}
                  <span class="superset-badge">Superset {rows[id].superset_group}</span>
                {/if}
              </span>
              <button class="link" onclick={() => removeFromSession(id)}>✕ remove</button>
            </div>
            <div class="inputs">
              <span><label>Sets</label><input type="number" bind:value={rows[id].sets} /></span>
              <span
                ><label>Hold (s)</label><input
                  type="number"
                  bind:value={rows[id].hold_seconds}
                /></span
              >
              <span><label>Reps</label><input type="number" bind:value={rows[id].reps} /></span>
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
              <span class="wide"
                ><label>Superset</label><select bind:value={rows[id].superset_group}>
                  <option value={null}>Not in a superset</option>
                  {#each supersetGroups(sessionLogs) as group}
                    <option value={group}>Superset {group}</option>
                  {/each}
                  <option value={nextSupersetGroup(sessionLogs)}>New superset</option>
                </select></span
              >
            </div>
          </div>
        {/each}
      </div>
      {#if invalidGroups.length}
        <p class="superset-warning" role="alert">
          Add another exercise to {invalidGroups.map((group) => `Superset ${group}`).join(', ')}.
        </p>
      {/if}
      <div class="row" style="margin-top: 0.75rem">
        <div class="field f-intensity">
          <label>Intensity (1–10)</label>
          <input type="number" min="1" max="10" step="0.5" bind:value={intensity} />
        </div>
        <div class="field" style="flex: 1">
          <label>Session notes</label>
          <input bind:value={sessionNotes} />
        </div>
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
      <div class="row">
        <button
          class="status-G"
          onclick={saveSession}
          disabled={(!added.length && !editingId) || !!invalidGroups.length}
          >{busy ? 'Saving…' : editingId ? 'Update session' : 'Save session'}</button
        >
        <button
          onclick={() =>
            createWorkout(
              added.map((id) => rows[id]),
              false
            )}
          disabled={!added.length}>Save as new workout</button
        >
      </div>
    </fieldset>
  </div>
{/if}

<div class="card">
  <h3 style="margin-top: 0">Catalogue</h3>
  <div class="row" style="margin-bottom: 0.75rem">
    <input bind:value={newExercise} placeholder="Add new exercise" style="flex: 1" />
    <button onclick={addExercise}>Add</button>
  </div>
  <ul class="cat">
    {#each exercises.filter((e) => e.active) as e}
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
  fieldset {
    border: 0;
    padding: 0;
    margin: 0;
    min-width: 0;
  }
  details {
    margin-bottom: 0.75rem;
  }
  .exrow {
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 0.6rem 0.75rem;
    margin-bottom: 0.5rem;
  }
  .exrow.on {
    border-color: var(--accent);
  }
  .exrow.superset {
    border-left-width: 4px;
  }
  .superset-badge {
    border-radius: 999px;
    background: var(--accent);
    color: var(--surface);
    padding: 0.1rem 0.45rem;
    font-size: 0.72rem;
    font-weight: 600;
  }
  .superset-warning {
    color: var(--danger, #c0392b);
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
  .inputs input,
  .inputs select {
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
    flex-wrap: wrap;
    gap: 0.5rem;
    align-items: center;
    justify-content: space-between;
  }
  .logged-when {
    font-weight: 600;
    color: var(--text);
  }
  .logged-actions {
    display: flex;
    flex-wrap: wrap;
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
    flex: none;
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
