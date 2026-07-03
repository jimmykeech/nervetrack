// Pure time/formatting helpers. Kept dependency-free so they are unit-testable.

import type { Interval, Posture, PostureTotals } from './types';

/** Format a number of seconds as "1h 23m 45s" / "23m 45s" / "45s". */
export function formatDuration(totalSeconds: number): string {
  const s = Math.max(0, Math.floor(totalSeconds));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  if (h > 0) return `${h}h ${m}m ${sec}s`;
  if (m > 0) return `${m}m ${sec}s`;
  return `${sec}s`;
}

/** Compact form for totals: "3h 12m" / "40m". */
export function formatMinutesish(totalSeconds: number): string {
  const s = Math.max(0, Math.floor(totalSeconds));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  if (h > 0) return `${h}h ${m.toString().padStart(2, '0')}m`;
  return `${m}m`;
}

/** Elapsed seconds of an interval; if running, measured against `now`. */
export function intervalSeconds(interval: Interval, now: number = Date.now()): number {
  if (interval.duration_seconds != null && interval.ended_at != null) {
    return interval.duration_seconds;
  }
  const start = Date.parse(interval.started_at + 'Z');
  return Math.max(0, Math.floor((now - start) / 1000));
}

/**
 * Per-posture totals for a day, counting the running interval's live elapsed
 * time. Mirrors the server's stored totals but stays correct between ticks.
 */
export function liveTotals(intervals: Interval[], now: number = Date.now()): PostureTotals {
  const totals: PostureTotals = { sitting: 0, standing: 0, lying: 0, walking: 0 };
  for (const iv of intervals) {
    totals[iv.posture] += intervalSeconds(iv, now);
  }
  return totals;
}

/** Sitting : standing ratio as a display string, e.g. "1.8 : 1". */
export function sitStandRatio(totals: PostureTotals): string {
  const { sitting, standing } = totals;
  if (standing === 0) return sitting === 0 ? '—' : '∞ : 1';
  return `${(sitting / standing).toFixed(1)} : 1`;
}

export const POSTURES: Posture[] = ['sitting', 'standing', 'lying', 'walking'];

export const POSTURE_LABEL: Record<Posture, string> = {
  sitting: 'Sitting',
  standing: 'Standing',
  lying: 'Lying',
  walking: 'Walking'
};

/** Today's date as YYYY-MM-DD in the browser's local timezone. */
export function todayISO(): string {
  const d = new Date();
  return toISODate(d);
}

export function toISODate(d: Date): string {
  const y = d.getFullYear();
  const m = (d.getMonth() + 1).toString().padStart(2, '0');
  const day = d.getDate().toString().padStart(2, '0');
  return `${y}-${m}-${day}`;
}

export function shiftISODate(iso: string, days: number): string {
  const d = new Date(iso + 'T00:00:00');
  d.setDate(d.getDate() + days);
  return toISODate(d);
}

/** Parse a free-text duration like "2hrs" or "30min" to minutes (or null). */
export function parseDurationToMinutes(input: string): number | null {
  const s = input.trim().toLowerCase();
  if (!s) return null;
  const re = /(\d+(?:\.\d+)?)\s*(h|hr|hrs|hour|hours|m|min|mins|minutes)?/g;
  let total = 0;
  let matched = false;
  let match: RegExpExecArray | null;
  while ((match = re.exec(s)) !== null) {
    if (!match[1]) continue;
    const num = parseFloat(match[1]);
    const unit = match[2] ?? '';
    if (unit === '' || unit.startsWith('h')) total += num * 60;
    else total += num;
    matched = true;
  }
  return matched ? Math.round(total) : null;
}

export function formatMinutesLabel(minutes: number | null): string {
  if (minutes == null) return '';
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  if (h > 0 && m > 0) return `${h}h ${m}m`;
  if (h > 0) return `${h}h`;
  return `${m}m`;
}

/** Combine a local YYYY-MM-DD date and HH:MM time into a UTC ISO string. */
export function combineDateTimeToISO(dateISO: string, hhmm: string): string {
  const [y, m, d] = dateISO.split('-').map(Number);
  const [hh, mm] = hhmm.split(':').map(Number);
  return new Date(y, m - 1, d, hh, mm, 0, 0).toISOString();
}

/**
 * Default time for the jab picker on a given day: the current local time when
 * `dateISO` is today, otherwise noon (there is no "now" within a past day).
 */
export function defaultJabTime(dateISO: string, now: Date = new Date()): string {
  if (dateISO !== todayISO()) return '12:00';
  const hh = now.getHours().toString().padStart(2, '0');
  const mm = now.getMinutes().toString().padStart(2, '0');
  return `${hh}:${mm}`;
}

/** Trim a user-entered interval label; empty/whitespace becomes null (clears it). */
export function normalizeLabel(input: string | null | undefined): string | null {
  const s = (input ?? '').trim();
  return s === '' ? null : s;
}

/** True when an interval's end is strictly after its start (ISO datetime strings). */
export function endsAfterStart(startIso: string, endIso: string): boolean {
  return new Date(endIso).getTime() > new Date(startIso).getTime();
}
