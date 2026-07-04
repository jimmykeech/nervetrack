import { describe, expect, it } from 'vitest';
import {
  MINUTES_PER_DAY,
  localDayStartMs,
  intervalToSegment,
  postureSegments,
  tinglingSegments,
  nowPct
} from './timelineBar';
import type { Interval, TinglingInterval } from './types';

// All geometry tests use dayStart = epoch 0 so `Date.parse(iso + 'Z')` (UTC)
// yields deterministic positions independent of the test runner's timezone.
const DAY0 = 0;
const H = 3_600_000; // one hour in ms

describe('MINUTES_PER_DAY', () => {
  it('is 1440', () => expect(MINUTES_PER_DAY).toBe(1440));
});

describe('localDayStartMs', () => {
  it('returns local midnight for the date', () => {
    const d = new Date(localDayStartMs('2026-07-04'));
    expect(d.getFullYear()).toBe(2026);
    expect(d.getMonth()).toBe(6); // July, 0-indexed
    expect(d.getDate()).toBe(4);
    expect(d.getHours()).toBe(0);
    expect(d.getMinutes()).toBe(0);
  });
});

describe('intervalToSegment', () => {
  it('positions a completed interval by start and end', () => {
    const g = intervalToSegment('1970-01-01T06:00:00', '1970-01-01T12:00:00', DAY0, 0)!;
    expect(g.leftPct).toBeCloseTo(25);
    expect(g.widthPct).toBeCloseTo(25);
    expect(g.startMs).toBe(6 * H);
    expect(g.endMs).toBe(12 * H);
  });

  it('extends a running interval to now', () => {
    const g = intervalToSegment('1970-01-01T06:00:00', null, DAY0, 9 * H)!;
    expect(g.leftPct).toBeCloseTo(25);
    expect(g.widthPct).toBeCloseTo(12.5);
    expect(g.endMs).toBe(9 * H);
  });

  it('clamps a running interval that crosses midnight to end of day', () => {
    const g = intervalToSegment('1970-01-01T22:00:00', null, DAY0, 25 * H)!;
    expect(g.leftPct).toBeCloseTo(91.6667);
    expect(g.widthPct).toBeCloseTo(8.3333);
    expect(g.endMs).toBe(MINUTES_PER_DAY * 60_000);
  });

  it('clamps a segment that started before midnight to start of day', () => {
    const g = intervalToSegment('1969-12-31T23:00:00', '1970-01-01T01:00:00', DAY0, 0)!;
    expect(g.leftPct).toBeCloseTo(0);
    expect(g.widthPct).toBeCloseTo(4.1667);
    expect(g.startMs).toBe(0);
  });

  it('returns null when the interval has no width within the day', () => {
    expect(intervalToSegment('1969-12-31T22:00:00', '1969-12-31T23:00:00', DAY0, 0)).toBeNull();
  });
});

describe('postureSegments', () => {
  it('maps intervals to segments carrying their posture, dropping empties', () => {
    const intervals = [
      { id: 'a', posture: 'sitting', started_at: '1970-01-01T00:00:00', ended_at: '1970-01-01T06:00:00', duration_seconds: 21600 },
      { id: 'b', posture: 'standing', started_at: '1970-01-01T06:00:00', ended_at: null, duration_seconds: null }
    ] as unknown as Interval[];
    const segs = postureSegments(intervals, DAY0, 12 * H);
    expect(segs.map((s) => s.posture)).toEqual(['sitting', 'standing']);
    expect(segs[0].widthPct).toBeCloseTo(25);
    expect(segs[1].widthPct).toBeCloseTo(25);
  });
});

describe('tinglingSegments', () => {
  it('maps intervals to segments carrying their level', () => {
    const intervals = [
      { id: 't', level: 6, started_at: '1970-01-01T09:00:00', ended_at: '1970-01-01T10:00:00', duration_seconds: 3600 }
    ] as unknown as TinglingInterval[];
    const segs = tinglingSegments(intervals, DAY0, 0);
    expect(segs).toHaveLength(1);
    expect(segs[0].level).toBe(6);
    expect(segs[0].leftPct).toBeCloseTo(37.5);
  });
});

describe('nowPct', () => {
  it('returns the percent of day for now', () => {
    expect(nowPct(DAY0, 6 * H)).toBeCloseTo(25);
  });
  it('clamps below 0 and above 100', () => {
    expect(nowPct(DAY0, -H)).toBe(0);
    expect(nowPct(DAY0, 30 * H)).toBe(100);
  });
});
