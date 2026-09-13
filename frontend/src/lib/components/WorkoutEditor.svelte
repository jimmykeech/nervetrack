<script lang="ts">
  import { untrack } from 'svelte';
  import { api } from '$lib/api';
  import type { Exercise, Workout, WorkoutIn } from '$lib/types';
  import {
    invalidSupersetGroups,
    nextSupersetGroup,
    supersetGroups,
    workoutExercises
  } from '$lib/workouts';

  let {
    exercises,
    initial,
    workoutId,
    useAfterSave,
    onSave,
    onCancel
  }: {
    exercises: Exercise[];
    initial: WorkoutIn;
    workoutId: string | null;
    useAfterSave: boolean;
    onSave: (workout: Workout) => void;
    onCancel: () => void;
  } = $props();

  // The parent keys the editor by draft, so each opening gets its own copy.
  let name = $state(untrack(() => initial.name));
  let rows = $state(untrack(() => workoutExercises(initial.exercises)));
  let toAdd = $state('');
  let busy = $state(false);
  let error = $state('');
  const available = $derived(
    exercises.filter(
      (exercise) => exercise.active && !rows.some((row) => row.exercise_id === exercise.id)
    )
  );
  const invalidGroups = $derived(invalidSupersetGroups(rows));

  function addExercise() {
    const exercise = available.find((item) => item.id === toAdd);
    if (!exercise) return;
    rows = [
      ...rows,
      {
        exercise_id: exercise.id,
        exercise_name: exercise.name,
        sets: null,
        reps: null,
        hold_seconds: null,
        weight_kg: null,
        modification: null,
        superset_group: null
      }
    ];
    toAdd = '';
  }

  async function save(event: SubmitEvent) {
    event.preventDefault();
    if (busy || !name.trim() || !rows.length || invalidGroups.length) return;
    busy = true;
    error = '';
    try {
      const data = { name: name.trim(), exercises: workoutExercises(rows) };
      const workout = workoutId
        ? await api.updateWorkout(workoutId, data)
        : await api.createWorkout(data);
      onSave(workout);
    } catch (e) {
      error = e instanceof Error ? e.message : 'Could not save workout.';
    } finally {
      busy = false;
    }
  }
</script>

<div class="card">
  <h3>{workoutId ? 'Edit workout' : 'Create workout'}</h3>
  <p class="muted small">Save your exercises and targets, then use them to log a session.</p>
  <form onsubmit={save}>
    <fieldset disabled={busy}>
      <label for="workout-name">Workout name</label>
      <input
        id="workout-name"
        bind:value={name}
        required
        maxlength="200"
        placeholder="e.g. Lower body"
      />
      <div class="row picker">
        <select aria-label="Exercise to add to workout" bind:value={toAdd}>
          <option value="">Choose an exercise…</option>
          {#each available as exercise (exercise.id)}
            <option value={exercise.id}>{exercise.name}</option>
          {/each}
        </select>
        <button type="button" onclick={addExercise} disabled={!toAdd}>Add exercise</button>
      </div>
      {#each rows as row, i (row.exercise_id)}
        <div class="exercise">
          <div class="row">
            <strong
              >{row.exercise_name ?? exercises.find((e) => e.id === row.exercise_id)?.name}</strong
            >
            <button type="button" onclick={() => (rows = rows.filter((_, index) => index !== i))}
              >Remove</button
            >
          </div>
          <div class="inputs">
            <label>Sets<input type="number" min="0" bind:value={row.sets} /></label>
            <label>Reps<input type="number" min="0" bind:value={row.reps} /></label>
            <label>Hold (s)<input type="number" min="0" bind:value={row.hold_seconds} /></label>
            <label
              >Weight (kg)<input
                type="number"
                min="0"
                step="any"
                bind:value={row.weight_kg}
              /></label
            >
            <label class="wide">Modification<input bind:value={row.modification} /></label>
            <label class="wide"
              >Superset
              <select bind:value={row.superset_group}>
                <option value={null}>Not in a superset</option>
                {#each supersetGroups(rows) as group}
                  <option value={group}>Superset {group}</option>
                {/each}
                <option value={nextSupersetGroup(rows)}>New superset</option>
              </select></label
            >
          </div>
        </div>
      {:else}
        <p class="muted small">Add at least one exercise to this workout.</p>
      {/each}
      {#if invalidGroups.length}
        <p class="superset-warning" role="alert">
          Add another exercise to {invalidGroups.map((group) => `Superset ${group}`).join(', ')}.
        </p>
      {/if}
      {#if error}<p role="alert">{error}</p>{/if}
      <div class="row">
        <button
          class="status-G"
          type="submit"
          disabled={!name.trim() || !rows.length || !!invalidGroups.length}
        >
          {busy ? 'Saving…' : useAfterSave ? 'Save workout & use' : 'Save workout'}
        </button>
        <button type="button" onclick={onCancel}>Cancel</button>
      </div>
    </fieldset>
  </form>
</div>

<style>
  h3 {
    margin-top: 0;
  }
  fieldset {
    border: 0;
    padding: 0;
    margin: 0;
    min-width: 0;
  }
  .picker {
    margin: 0.75rem 0;
  }
  .picker select {
    flex: 1;
    min-width: 0;
  }
  .exercise {
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 0.75rem;
    margin-bottom: 0.75rem;
  }
  .exercise .row {
    justify-content: space-between;
  }
  .inputs {
    display: flex;
    flex-wrap: wrap;
    gap: 0.5rem;
    margin-top: 0.5rem;
  }
  .inputs label {
    flex: 1 1 4.5rem;
  }
  .inputs .wide {
    flex-basis: 12rem;
  }
  input,
  .inputs select {
    width: 100%;
  }
  .superset-warning {
    color: var(--danger, #c0392b);
  }
</style>
