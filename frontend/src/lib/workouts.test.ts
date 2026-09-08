import { expect, it } from 'vitest';
import type { ExerciseLog } from './types';
import { workoutExercises, workoutLogs } from './workouts';

it('reuses session targets without copying outcomes or sharing edits with the saved workout', () => {
  const logged: ExerciseLog = {
    id: 'old-log',
    exercise_id: 'bridge',
    exercise_name: 'Bridge',
    sets: 3,
    reps: 10,
    hold_seconds: 5,
    weight_kg: 2.5,
    modification: 'Heel elevation',
    difficulty: 7,
    nerve_response: 'Twinge'
  };
  const saved = workoutExercises([logged, { ...logged, exercise_id: 'plank' }]);
  const session = workoutLogs(saved);

  expect(session.map((log) => log.exercise_id)).toEqual(['bridge', 'plank']);
  expect(saved[0]).not.toHaveProperty('id');
  expect(saved[0]).not.toHaveProperty('difficulty');
  expect(saved[0]).not.toHaveProperty('nerve_response');
  expect(session[0]).toEqual({ ...saved[0], difficulty: null, nerve_response: null });
  expect(session[0]).toMatchObject({
    sets: 3,
    reps: 10,
    hold_seconds: 5,
    weight_kg: 2.5,
    modification: 'Heel elevation'
  });

  session[0].sets = 5;
  expect(saved[0].sets).toBe(3);
  saved[0].reps = 12;
  expect(logged.reps).toBe(10);
  expect(workoutLogs(saved)[0].sets).toBe(3);
});
