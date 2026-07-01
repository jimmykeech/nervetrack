// Shared pain-instance catalogue, loaded once from the root layout and read
// by the Today/Exercises tagging UI, the Settings management section, and
// the first-login onboarding gate.

import { api } from '$lib/api';
import type { PainInstance } from '$lib/types';

export const painInstances = $state<{ list: PainInstance[]; loaded: boolean }>({
  list: [],
  loaded: false
});

export async function loadPainInstances(): Promise<PainInstance[]> {
  painInstances.list = await api.listPainInstances();
  painInstances.loaded = true;
  return painInstances.list;
}

export function activePainInstances(): PainInstance[] {
  return painInstances.list.filter((i) => i.active);
}
