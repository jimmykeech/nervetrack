export type Theme = 'light' | 'dark';

export function resolveInitialTheme(stored: string | null, system: Theme): Theme {
  return stored === 'light' || stored === 'dark' ? stored : system;
}

export function nextTheme(t: Theme): Theme {
  return t === 'light' ? 'dark' : 'light';
}
