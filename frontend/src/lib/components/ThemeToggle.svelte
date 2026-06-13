<script lang="ts">
  import { themeState, toggleTheme } from '$lib/stores/theme.svelte';
</script>

<button class="theme" onclick={toggleTheme} aria-label="Toggle light/dark theme" title="Toggle theme">
  {themeState.theme === 'dark' ? '☾' : '☀'}
</button>

<style>
  .theme {
    width: 2.2rem;
    height: 2.2rem;
    padding: 0;
    border-radius: var(--r-pill);
    font-size: 1rem;
    line-height: 1;
  }
</style>
