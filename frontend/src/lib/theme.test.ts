import { describe, expect, it } from 'vitest';
import { resolveInitialTheme, nextTheme } from './theme';

describe('resolveInitialTheme', () => {
  it('uses a valid stored value over system', () => {
    expect(resolveInitialTheme('light', 'dark')).toBe('light');
    expect(resolveInitialTheme('dark', 'light')).toBe('dark');
  });
  it('falls back to system when stored is missing/invalid', () => {
    expect(resolveInitialTheme(null, 'light')).toBe('light');
    expect(resolveInitialTheme('purple', 'dark')).toBe('dark');
  });
});

describe('nextTheme', () => {
  it('toggles', () => {
    expect(nextTheme('light')).toBe('dark');
    expect(nextTheme('dark')).toBe('light');
  });
});
