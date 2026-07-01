import { describe, expect, it } from 'vitest';
import { buildTimeline } from './timeline';
import type { DailyEntry } from './types';

function entry(overrides: Partial<DailyEntry>): DailyEntry {
  return {
    id: 'e1',
    entry_date: '2026-06-13',
    status: null,
    strengthening_done: false,
    session_intensity: null,
    sharp_pain_episodes: 0,
    worst_pain: null,
    tingling_level: null,
    tingling_duration_minutes: null,
    stretches_morning: false,
    stretches_night: false,
    sitting_breaks: null,
    sleep_quality: null,
    iced: false,
    strengthening_done_at: null,
    stretches_morning_at: null,
    stretches_night_at: null,
    iced_at: null,
    pain_events: [],
    notes: [],
    session: null,
    timer_totals: { sitting: 0, standing: 0, lying: 0, walking: 0 },
    timer_intervals: [],
    ...overrides
  };
}

describe('buildTimeline', () => {
  it('returns [] for an empty day', () => {
    expect(buildTimeline(entry({}))).toEqual([]);
  });

  it('merges and sorts all sources newest first (descending) by time', () => {
    const events = buildTimeline(
      entry({
        stretches_morning_at: '2026-06-13T07:45:00',
        iced_at: '2026-06-13T20:00:00',
        pain_events: [
          {
            id: 'p1',
            daily_entry_id: 'e1',
            occurred_at: '2026-06-13T11:15:00',
            pain_level: 4,
            context: 'desk',
            instance_ids: []
          }
        ],
        notes: [
          {
            id: 'n1',
            daily_entry_id: 'e1',
            occurred_at: '2026-06-13T14:20:00',
            body: 'tightness',
            source: null,
            created_at: null,
            updated_at: null
          }
        ],
        timer_intervals: [
          {
            id: 'i1',
            entry_date: '2026-06-13',
            posture: 'sitting',
            started_at: '2026-06-13T09:02:00',
            ended_at: '2026-06-13T10:20:00',
            duration_seconds: 4680,
            label: null
          }
        ]
      })
    );
    expect(events.map((e) => e.kind)).toEqual(['check', 'note', 'pain', 'timer', 'check']);
    expect(events.map((e) => e.at)).toEqual([
      '2026-06-13T20:00:00',
      '2026-06-13T14:20:00',
      '2026-06-13T11:15:00',
      '2026-06-13T09:02:00',
      '2026-06-13T07:45:00'
    ]);
  });

  it('carries the timer interval label onto the timer event', () => {
    const events = buildTimeline(
      entry({
        timer_intervals: [
          {
            id: 'i1',
            entry_date: '2026-06-13',
            posture: 'sitting',
            started_at: '2026-06-13T09:02:00',
            ended_at: '2026-06-13T10:20:00',
            duration_seconds: 4680,
            label: 'watching tv on couch'
          },
          {
            id: 'i2',
            entry_date: '2026-06-13',
            posture: 'standing',
            started_at: '2026-06-13T11:00:00',
            ended_at: null,
            duration_seconds: null,
            label: null
          }
        ]
      })
    );
    expect(events).toMatchObject([
      { kind: 'timer', label: null },
      { kind: 'timer', label: 'watching tv on couch' }
    ]);
  });

  it('flags a running interval and excludes null checkbox times', () => {
    const events = buildTimeline(
      entry({
        timer_intervals: [
          {
            id: 'i1',
            entry_date: '2026-06-13',
            posture: 'standing',
            started_at: '2026-06-13T09:00:00',
            ended_at: null,
            duration_seconds: null,
            label: null
          }
        ]
      })
    );
    expect(events).toHaveLength(1);
    expect(events[0]).toMatchObject({ kind: 'timer', running: true });
  });
});
