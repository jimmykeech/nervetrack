import js from '@eslint/js';
import ts from 'typescript-eslint';
import svelte from 'eslint-plugin-svelte';
import svelteParser from 'svelte-eslint-parser';
import globals from './eslint.globals.js';

export default [
  js.configs.recommended,
  ...ts.configs.recommended,
  ...svelte.configs['flat/recommended'],
  {
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: 'module',
      globals
    }
  },
  {
    files: ['**/*.svelte'],
    languageOptions: {
      parser: svelteParser,
      parserOptions: { parser: ts.parser }
    }
  },
  {
    rules: {
      // The DuckDB/JSON boundary is loosely typed; allow pragmatic `any`.
      '@typescript-eslint/no-explicit-any': 'off',
      'no-undef': 'off',
      // svelte-check (`npm run check`) owns compile/a11y validation; keeping it
      // here too would double-report the intentional caption-label warnings.
      'svelte/valid-compile': 'off'
    }
  },
  {
    ignores: ['.svelte-kit/', 'build/', 'node_modules/', 'eslint.globals.js']
  }
];
