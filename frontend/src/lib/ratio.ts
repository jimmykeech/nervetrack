import type { Posture, PostureTotals } from '$lib/types';

export interface RatioSegment {
  posture: Posture;
  seconds: number;
  percent: number;
}

const ORDER: Posture[] = ['sitting', 'standing', 'lying', 'walking'];

export function ratioSegments(totals: PostureTotals): RatioSegment[] {
  const total = ORDER.reduce((sum, p) => sum + totals[p], 0);
  if (total === 0) return [];
  return ORDER.filter((p) => totals[p] > 0).map((p) => ({
    posture: p,
    seconds: totals[p],
    percent: (totals[p] / total) * 100
  }));
}
