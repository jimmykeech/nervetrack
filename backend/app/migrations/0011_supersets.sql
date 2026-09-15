-- Preserve session exercise order and allow independent superset groups.
ALTER TABLE exercise_logs ADD COLUMN sort_order INTEGER CHECK (sort_order >= 0);
ALTER TABLE exercise_logs ADD COLUMN superset_group INTEGER CHECK (superset_group >= 1);
ALTER TABLE workout_exercises ADD COLUMN superset_group INTEGER CHECK (superset_group >= 1);
