-- Reusable workout plans are independent of completed strength sessions.
CREATE TABLE workouts (
    id UUID PRIMARY KEY DEFAULT (gen_random_uuid()),
    user_id UUID NOT NULL REFERENCES users (id),
    name TEXT NOT NULL
);

CREATE INDEX workouts_user_id ON workouts (user_id);

CREATE TABLE workout_exercises (
    workout_id UUID NOT NULL REFERENCES workouts (id) ON DELETE CASCADE,
    exercise_id UUID NOT NULL REFERENCES exercises (id),
    sort_order INTEGER NOT NULL,
    sets INTEGER CHECK (sets >= 0),
    reps INTEGER CHECK (reps >= 0),
    hold_seconds INTEGER CHECK (hold_seconds >= 0),
    weight_kg DECIMAL(4, 1) CHECK (weight_kg >= 0),
    modification TEXT,
    PRIMARY KEY (workout_id, exercise_id),
    UNIQUE (workout_id, sort_order)
);
