import { describe, expect, it } from 'vitest';
import { ratioSegments } from './ratio';

describe('ratioSegments', () => {
  it('returns [] when nothing is tracked', () => {
    expect(ratioSegments({ sitting: 0, standing: 0, lying: 0, walking: 0 })).toEqual([]);
  });
  it('computes percentages in posture order, skipping zeros', () => {
    const segs = ratioSegments({ sitting: 300, standing: 100, lying: 0, walking: 0 });
    expect(segs.map((s) => s.posture)).toEqual(['sitting', 'standing']);
    expect(segs[0].percent).toBeCloseTo(75);
    expect(segs[1].percent).toBeCloseTo(25);
    expect(segs.reduce((t, s) => t + s.percent, 0)).toBeCloseTo(100);
  });
});
