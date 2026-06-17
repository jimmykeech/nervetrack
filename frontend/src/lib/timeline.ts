// Flattens a DailyEntry's four event sources into a single chronological list.
// Pure and dependency-free so it is unit-testable. Timestamps are naive UTC
// ISO strings of uniform format, so lexical comparison orders them correctly.

import type { DailyEntry, Posture } from './types';

export type TimelineEvent =
  | {
      kind: 'timer';
      at: string;
      posture: Posture;
      durationSeconds: number | null;
      running: boolean;
    }
  | { kind: 'pain'; at: string; level: number | null; context: string | null }
  | { kind: 'check'; at: string; label: string }
  | { kind: 'note'; at: string; id: string; body: string };

const CHECKBOX_FIELDS: [keyof DailyEntry, string][] = [
  ['strengthening_done_at', 'Strengthening session'],
  ['stretches_morning_at', 'Stretches — morning'],
  ['stretches_night_at', 'Stretches — night'],
  ['iced_at', 'Iced piriformis']
];

export function buildTimeline(entry: DailyEntry): TimelineEvent[] {
  const events: TimelineEvent[] = [];

  for (const iv of entry.timer_intervals) {
    events.push({
      kind: 'timer',
      at: iv.started_at,
      posture: iv.posture,
      durationSeconds: iv.duration_seconds,
      running: iv.ended_at == null
    });
  }

  for (const p of entry.pain_events) {
    events.push({ kind: 'pain', at: p.occurred_at, level: p.pain_level, context: p.context });
  }

  for (const [field, label] of CHECKBOX_FIELDS) {
    const at = entry[field] as string | null;
    if (at) events.push({ kind: 'check', at, label });
  }

  for (const n of entry.notes) {
    events.push({ kind: 'note', at: n.occurred_at, id: n.id, body: n.body });
  }

  return events.sort((a, b) => (a.at < b.at ? -1 : a.at > b.at ? 1 : 0));
}
