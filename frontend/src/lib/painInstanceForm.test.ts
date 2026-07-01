import { describe, expect, it } from 'vitest';
import { blankPainInstanceDraft, filledDrafts, hasValidDraft } from './painInstanceForm';

describe('painInstanceForm', () => {
  it('blank draft has empty fields', () => {
    expect(blankPainInstanceDraft()).toEqual({ name: '', body_region: '', background: '' });
  });

  it('hasValidDraft is false when every name is blank or whitespace', () => {
    expect(hasValidDraft([{ name: '', body_region: '', background: '' }])).toBe(false);
    expect(hasValidDraft([{ name: '   ', body_region: '', background: '' }])).toBe(false);
  });

  it('hasValidDraft is true when at least one name is non-empty', () => {
    expect(
      hasValidDraft([
        { name: '', body_region: '', background: '' },
        { name: 'Left sciatic', body_region: '', background: '' }
      ])
    ).toBe(true);
  });

  it('filledDrafts keeps only drafts with a non-empty trimmed name', () => {
    const drafts = [
      { name: 'Left sciatic', body_region: 'Hip', background: '' },
      { name: '  ', body_region: '', background: '' }
    ];
    expect(filledDrafts(drafts)).toEqual([drafts[0]]);
  });
});
