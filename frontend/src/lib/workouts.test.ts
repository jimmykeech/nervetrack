import { expect, it } from 'vitest';
import type { ExerciseLog } from './types';
import {
  invalidSupersetGroups,
  nextSupersetGroup,
  supersetGroups,
  workoutExercises,
  workoutLogs
} from './workouts';

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
    nerve_response: 'Twinge',
    superset_group: 1
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
    modification: 'Heel elevation',
    superset_group: 1
  });

  session[0].sets = 5;
  expect(saved[0].sets).toBe(3);
  saved[0].reps = 12;
  expect(logged.reps).toBe(10);
  expect(workoutLogs(saved)[0].sets).toBe(3);
});

it('supports multiple independent supersets and detects incomplete groups', () => {
  const exercises = [
    { superset_group: 1 },
    { superset_group: 1 },
    { superset_group: 2 },
    { superset_group: 2 },
    { superset_group: null }
  ];
  expect(supersetGroups(exercises)).toEqual([1, 2]);
  expect(nextSupersetGroup(exercises)).toBe(3);
  expect(invalidSupersetGroups(exercises)).toEqual([]);
  expect(invalidSupersetGroups([...exercises, { superset_group: 3 }])).toEqual([3]);
});
