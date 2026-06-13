// Applies the chosen theme to <html data-theme> and persists the user's choice.
// First visit follows the OS preference; an explicit toggle is remembered.

import { resolveInitialTheme, nextTheme, type Theme } from '$lib/theme';

const KEY = 'nervetrack-theme';

export const themeState = $state<{ theme: Theme }>({ theme: 'dark' });

function systemTheme(): Theme {
  return window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark';
}

function apply(t: Theme): void {
  themeState.theme = t;
  document.documentElement.setAttribute('data-theme', t);
}

export function initTheme(): void {
  apply(resolveInitialTheme(localStorage.getItem(KEY), systemTheme()));
}

export function toggleTheme(): void {
  const t = nextTheme(themeState.theme);
  apply(t);
  localStorage.setItem(KEY, t); // only an explicit choice is persisted
}
