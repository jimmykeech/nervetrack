<script lang="ts">
  import '@fontsource-variable/fraunces';
  import '@fontsource-variable/hanken-grotesk';
  import '../app.css';
  import { onMount } from 'svelte';
  import { page } from '$app/stores';
  import { goto } from '$app/navigation';
  import { auth, loadUser, signOut } from '$lib/stores/auth.svelte';
  import PainInstanceOnboarding from '$lib/components/PainInstanceOnboarding.svelte';
  import ThemeToggle from '$lib/components/ThemeToggle.svelte';
  import { initTheme } from '$lib/stores/theme.svelte';
  import { loadPainInstances, painInstances } from '$lib/stores/painInstances.svelte';

  let { children } = $props();

  const nav = [
    { href: '/', label: 'Today' },
    { href: '/timer', label: 'Timer' },
    { href: '/history', label: 'History' },
    { href: '/exercises', label: 'Exercises' },
    { href: '/weekly', label: 'Weekly' },
    { href: '/chat', label: 'Chat' },
    { href: '/settings', label: 'Settings' }
  ];

  const isLogin = $derived($page.url.pathname === '/login');

  function isActive(href: string): boolean {
    const path = $page.url.pathname;
    return href === '/' ? path === '/' : path.startsWith(href);
  }

  onMount(async () => {
    initTheme();
    const user = await loadUser();
    // Only bounce to /login for a genuine "not signed in". On a backend error
    // stay put and surface it (see the error block in <main>) rather than
    // looping to a login page whose Google button hits the same failure.
    if (!user && !auth.error && !isLogin) goto('/login');
    if (user) await loadPainInstances();
  });

  async function handleLogout() {
    await signOut();
    goto('/login');
  }
</script>

{#if isLogin}
  <main class="bare">
    {@render children()}
  </main>
{:else}
  <div class="shell">
    <header>
      <div class="topline">
        <div class="brand">NerveTrack</div>
        <div class="account">
          <ThemeToggle />
          {#if auth.user}
            <span class="muted small">{auth.user.email}</span>
            <button class="logout" onclick={handleLogout}>Sign out</button>
          {/if}
        </div>
      </div>
      <nav>
        {#each nav as item}
          <a href={item.href} class:active={isActive(item.href)}>{item.label}</a>
        {/each}
      </nav>
    </header>
    <main>
      {#if auth.ready && auth.user}
        {#if !painInstances.loaded}
          <!-- brief gap while the pain-instance catalogue loads -->
        {:else if painInstances.list.length === 0}
          <PainInstanceOnboarding />
        {:else}
          {@render children()}
        {/if}
      {:else if auth.ready && auth.error}
        <div class="card loaderr">
          <p>Couldn’t reach the server.</p>
          <button onclick={() => location.reload()}>Retry</button>
        </div>
      {/if}
    </main>
  </div>
{/if}

<style>
  .shell {
    max-width: var(--maxw);
    margin: 0 auto;
    padding: 0 1rem 5rem;
  }
  .bare {
    max-width: var(--maxw);
    margin: 0 auto;
    padding: 0 1rem;
  }
  .loaderr {
    margin-top: 2rem;
    text-align: center;
  }
  .loaderr button {
    margin-top: 0.75rem;
  }
  header {
    position: sticky;
    top: 0;
    background: var(--bg);
    padding: 0.75rem 0;
    z-index: 10;
  }
  .topline {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 0.5rem;
  }
  .brand {
    font-family: var(--font-display);
    font-weight: 700;
    font-size: 1.25rem;
  }
  .account {
    display: flex;
    align-items: center;
    gap: 0.6rem;
  }
  .logout {
    padding: 0.3rem 0.7rem;
    font-size: 0.85rem;
  }
  nav {
    display: flex;
    gap: 0.35rem;
    overflow-x: auto;
    -webkit-overflow-scrolling: touch;
  }
  nav a {
    padding: 0.45rem 0.8rem;
    border-radius: 999px;
    color: var(--text-muted);
    white-space: nowrap;
    border: 1px solid transparent;
  }
  nav a.active {
    color: var(--text);
    background: var(--surface);
    border-color: var(--border);
  }
</style>
