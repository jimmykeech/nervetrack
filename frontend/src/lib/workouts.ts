import type { ExerciseLog, WorkoutExercise } from './types';

export function workoutExercises(logs: WorkoutExercise[]): WorkoutExercise[] {
  return logs.map((log) => ({
    exercise_id: log.exercise_id,
    exercise_name: log.exercise_name,
    sets: log.sets ?? null,
    reps: log.reps ?? null,
    hold_seconds: log.hold_seconds ?? null,
    weight_kg: log.weight_kg ?? null,
    modification: log.modification ?? null,
    superset_group: log.superset_group ?? null
  }));
}

export function workoutLogs(exercises: WorkoutExercise[]): ExerciseLog[] {
  return workoutExercises(exercises).map((exercise) => ({
    ...exercise,
    difficulty: null,
    nerve_response: null
  }));
}

type SupersetExercise = { superset_group: number | null };

export function supersetGroups(exercises: SupersetExercise[]): number[] {
  return [
    ...new Set(
      exercises.flatMap((exercise) =>
        exercise.superset_group === null ? [] : [exercise.superset_group]
      )
    )
  ].sort((a, b) => a - b);
}

export function nextSupersetGroup(exercises: SupersetExercise[]): number {
  const groups = supersetGroups(exercises);
  return groups.length ? Math.max(...groups) + 1 : 1;
}

export function invalidSupersetGroups(exercises: SupersetExercise[]): number[] {
  const counts = new Map<number, number>();
  for (const exercise of exercises) {
    if (exercise.superset_group !== null) {
      counts.set(exercise.superset_group, (counts.get(exercise.superset_group) ?? 0) + 1);
    }
  }
  return [...counts.entries()]
    .filter(([, count]) => count < 2)
    .map(([group]) => group)
    .sort((a, b) => a - b);
}
