// Pure geometry for the 24-hour timeline bar. Converts posture/tingling
// intervals into segments positioned as percentages of the day. Kept
// dependency-free and DOM-free so the cross-midnight and running-edge cases
// are unit-testable, mirroring ratio.ts.

import type { Interval, Posture, TinglingInterval } from './types';

export const MINUTES_PER_DAY = 1440;
const MS_PER_MINUTE = 60_000;
const MS_PER_DAY = MINUTES_PER_DAY * MS_PER_MINUTE;

/** Local-midnight epoch ms for a "YYYY-MM-DD" date string. */
export function localDayStartMs(date: string): number {
  const [y, m, d] = date.split('-').map(Number);
  return new Date(y, m - 1, d).getTime();
}

export interface BarGeometry {
  leftPct: number;
  widthPct: number;
  startMs: number;
  endMs: number;
}

/**
 * Position an interval within the [dayStart, dayStart + 24h) window as
 * percentages of the day. A running interval (ended_at null) ends at `now`.
 * Both edges are clamped to the day bounds; returns null when no visible
 * width remains within the day.
 */
export function intervalToSegment(
  startISO: string,
  endISO: string | null,
  dayStart: number,
  now: number
): BarGeometry | null {
  const dayEnd = dayStart + MS_PER_DAY;
  const rawStart = Date.parse(startISO + 'Z');
  const rawEnd = endISO != null ? Date.parse(endISO + 'Z') : now;
  const startMs = Math.max(rawStart, dayStart);
  const endMs = Math.min(rawEnd, dayEnd);
  if (endMs <= startMs) return null;
  const leftPct = ((startMs - dayStart) / MS_PER_DAY) * 100;
  const widthPct = ((endMs - startMs) / MS_PER_DAY) * 100;
  return { leftPct, widthPct, startMs, endMs };
}

export interface PostureBarSegment extends BarGeometry {
  posture: Posture;
}

export function postureSegments(
  intervals: Interval[],
  dayStart: number,
  now: number
): PostureBarSegment[] {
  const out: PostureBarSegment[] = [];
  for (const iv of intervals) {
    const g = intervalToSegment(iv.started_at, iv.ended_at, dayStart, now);
    if (g) out.push({ ...g, posture: iv.posture });
  }
  return out;
}

export interface TinglingBarSegment extends BarGeometry {
  level: number;
}

export function tinglingSegments(
  intervals: TinglingInterval[],
  dayStart: number,
  now: number
): TinglingBarSegment[] {
  const out: TinglingBarSegment[] = [];
  for (const iv of intervals) {
    const g = intervalToSegment(iv.started_at, iv.ended_at, dayStart, now);
    if (g) out.push({ ...g, level: iv.level });
  }
  return out;
}

/** Position of the `now` marker as a percentage of the day, clamped to [0, 100]. */
export function nowPct(dayStart: number, now: number): number {
  const pct = ((now - dayStart) / MS_PER_DAY) * 100;
  return Math.min(100, Math.max(0, pct));
}
