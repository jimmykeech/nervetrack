import { describe, expect, it } from 'vitest';
import {
  formatDuration,
  formatMinutesish,
  intervalSeconds,
  liveTotals,
  parseDurationToMinutes,
  shiftISODate,
  sitStandRatio
} from './time';
import type { Interval } from './types';

function iv(partial: Partial<Interval>): Interval {
  return {
    id: 'x',
    entry_date: '2026-06-13',
    posture: 'sitting',
    started_at: '2026-06-13T00:00:00',
    ended_at: null,
    duration_seconds: null,
    label: null,
    ...partial
  };
}

describe('formatDuration', () => {
  it('formats hours, minutes, seconds', () => {
    expect(formatDuration(5025)).toBe('1h 23m 45s');
    expect(formatDuration(125)).toBe('2m 5s');
    expect(formatDuration(9)).toBe('9s');
    expect(formatDuration(-5)).toBe('0s');
  });
});

describe('formatMinutesish', () => {
  it('renders compact totals', () => {
    expect(formatMinutesish(3 * 3600 + 12 * 60)).toBe('3h 12m');
    expect(formatMinutesish(40 * 60)).toBe('40m');
  });
});

describe('intervalSeconds', () => {
  it('uses stored duration for ended intervals', () => {
    expect(intervalSeconds(iv({ ended_at: '2026-06-13T00:10:00', duration_seconds: 600 }))).toBe(
      600
    );
  });

  it('measures live elapsed for running intervals', () => {
    const start = Date.parse('2026-06-13T00:00:00Z');
    const now = start + 90_000; // 90s later
    expect(intervalSeconds(iv({ started_at: '2026-06-13T00:00:00' }), now)).toBe(90);
  });
});

describe('liveTotals', () => {
  it('sums per posture and counts the running interval live', () => {
    const start = Date.parse('2026-06-13T00:00:00Z');
    const now = start + 120_000; // 2 min
    const totals = liveTotals(
      [
        iv({ posture: 'sitting', ended_at: '2026-06-13T00:05:00', duration_seconds: 300 }),
        iv({ posture: 'standing', ended_at: '2026-06-13T00:02:00', duration_seconds: 120 }),
        iv({ posture: 'sitting', started_at: '2026-06-13T00:00:00' }) // running, +120s
      ],
      now
    );
    expect(totals.sitting).toBe(420);
    expect(totals.standing).toBe(120);
    expect(totals.lying).toBe(0);
  });
});

describe('sitStandRatio', () => {
  it('computes ratio and edge cases', () => {
    expect(sitStandRatio({ sitting: 360, standing: 200, lying: 0, walking: 0 })).toBe('1.8 : 1');
    expect(sitStandRatio({ sitting: 0, standing: 0, lying: 0, walking: 0 })).toBe('—');
    expect(sitStandRatio({ sitting: 100, standing: 0, lying: 0, walking: 0 })).toBe('∞ : 1');
  });
});

describe('parseDurationToMinutes', () => {
  it('parses free-text durations', () => {
    expect(parseDurationToMinutes('2hrs')).toBe(120);
    expect(parseDurationToMinutes('30min')).toBe(30);
    expect(parseDurationToMinutes('1.5hr')).toBe(90);
    expect(parseDurationToMinutes('')).toBeNull();
  });
});

describe('shiftISODate', () => {
  it('shifts dates across month boundaries', () => {
    expect(shiftISODate('2026-06-13', -1)).toBe('2026-06-12');
    expect(shiftISODate('2026-06-30', 1)).toBe('2026-07-01');
  });
});
