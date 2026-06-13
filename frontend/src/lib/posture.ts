import type { Posture } from '$lib/types';

export const POSTURE_META: Record<Posture, { label: string; cssVar: string }> = {
  sitting: { label: 'Sitting', cssVar: '--posture-sitting' },
  standing: { label: 'Standing', cssVar: '--posture-standing' },
  lying: { label: 'Lying', cssVar: '--posture-lying' },
  walking: { label: 'Walking', cssVar: '--posture-walking' }
};

export function postureColor(p: Posture): string {
  return `var(${POSTURE_META[p].cssVar})`;
}
