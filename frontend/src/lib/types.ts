export type Status = 'G' | 'A' | 'R';
export type Posture = 'sitting' | 'standing' | 'lying' | 'walking';

export interface PostureTotals {
  sitting: number;
  standing: number;
  lying: number;
  walking: number;
}

export interface PainEvent {
  id: string;
  daily_entry_id: string;
  occurred_at: string;
  pain_level: number | null;
  context: string | null;
}

export interface Note {
  id: string;
  daily_entry_id: string;
  occurred_at: string;
  body: string;
  source: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface ExerciseLog {
  id?: string;
  exercise_id: string;
  exercise_name?: string | null;
  sets: number | null;
  reps: number | null;
  hold_seconds: number | null;
  weight_kg: number | null;
  difficulty: number | null;
  nerve_response: string | null;
  modification: string | null;
}

export interface SessionDetail {
  id: string;
  daily_entry_id: string;
  performed_at: string;
  intensity: number | null;
  notes: string | null;
  logs: ExerciseLog[];
}

export interface DailyEntry {
  id: string;
  entry_date: string;
  status: Status | null;
  strengthening_done: boolean;
  session_intensity: number | null;
  sharp_pain_episodes: number;
  worst_pain: number | null;
  tingling_level: number | null;
  tingling_duration_minutes: number | null;
  stretches_morning: boolean;
  stretches_night: boolean;
  sitting_breaks: string | null;
  sleep_quality: number | null;
  iced: boolean;
  strengthening_done_at: string | null;
  stretches_morning_at: string | null;
  stretches_night_at: string | null;
  iced_at: string | null;
  pain_events: PainEvent[];
  notes: Note[];
  session: SessionDetail | null;
  timer_totals: PostureTotals;
  timer_intervals: Interval[];
}

export interface DailyEntrySummary {
  entry_date: string;
  status: Status | null;
  strengthening_done: boolean;
  session_intensity: number | null;
  sharp_pain_episodes: number;
  worst_pain: number | null;
  tingling_level: number | null;
  sleep_quality: number | null;
  iced: boolean;
}

export interface Interval {
  id: string;
  entry_date: string;
  posture: Posture;
  started_at: string;
  ended_at: string | null;
  duration_seconds: number | null;
  label: string | null;
}

export interface DayTimer {
  entry_date: string;
  intervals: Interval[];
  totals: PostureTotals;
  running: Interval | null;
}

export interface Exercise {
  id: string;
  name: string;
  active: boolean;
  sort_order: number;
}

export interface WeeklyComputed {
  strengthening_sessions: number;
  avg_pain_episodes_per_day: number | null;
  avg_tingling_level: number | null;
  worst_pain: number | null;
  days_logged: number;
  red_days: number;
  amber_days: number;
  green_days: number;
  suggested_status: Status | null;
  sitting_minutes: number;
  standing_minutes: number;
}

export interface WeeklySummary {
  week_start: string;
  week_end: string;
  overall_status: Status | null;
  key_observations: string | null;
  trend_vs_last_week: string | null;
  computed: WeeklyComputed;
}

export interface DailyStatPoint {
  entry_date: string;
  sharp_pain_episodes: number;
  worst_pain: number | null;
  tingling_level: number | null;
  session_intensity: number | null;
  sitting_minutes: number;
  standing_minutes: number;
  lying_minutes: number;
  walking_minutes: number;
}
