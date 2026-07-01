// Pure helpers for the pain-instance draft form, shared by the mandatory
// first-login onboarding modal and the Settings management section.

export interface PainInstanceDraft {
  name: string;
  body_region: string;
  background: string;
}

export function blankPainInstanceDraft(): PainInstanceDraft {
  return { name: '', body_region: '', background: '' };
}

export function hasValidDraft(drafts: PainInstanceDraft[]): boolean {
  return drafts.some((d) => d.name.trim().length > 0);
}

export function filledDrafts(drafts: PainInstanceDraft[]): PainInstanceDraft[] {
  return drafts.filter((d) => d.name.trim().length > 0);
}
