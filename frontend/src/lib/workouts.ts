import type { ExerciseLog, WorkoutExercise } from './types';

export function workoutExercises(logs: WorkoutExercise[]): WorkoutExercise[] {
  return logs.map((log) => ({
    exercise_id: log.exercise_id,
    exercise_name: log.exercise_name,
    sets: log.sets ?? null,
    reps: log.reps ?? null,
    hold_seconds: log.hold_seconds ?? null,
    weight_kg: log.weight_kg ?? null,
    modification: log.modification ?? null
  }));
}

export function workoutLogs(exercises: WorkoutExercise[]): ExerciseLog[] {
  return workoutExercises(exercises).map((exercise) => ({
    ...exercise,
    difficulty: null,
    nerve_response: null
  }));
}
