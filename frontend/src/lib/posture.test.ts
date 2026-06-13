import { describe, expect, it } from 'vitest';
import { POSTURE_META, postureColor } from './posture';

describe('posture map', () => {
  it('covers all four postures with labels', () => {
    expect(Object.keys(POSTURE_META).sort()).toEqual(['lying', 'sitting', 'standing', 'walking']);
    expect(POSTURE_META.sitting.label).toBe('Sitting');
  });
  it('returns a css var() referencing the posture token', () => {
    expect(postureColor('sitting')).toBe('var(--posture-sitting)');
    expect(postureColor('standing')).toBe('var(--posture-standing)');
  });
});
