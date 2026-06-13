<script lang="ts">
  import '../app.css';
  import { onMount } from 'svelte';
  import { page } from '$app/stores';
  import { goto } from '$app/navigation';
  import { auth, loadUser, signOut } from '$lib/stores/auth.svelte';

  let { children } = $props();

  const nav = [
    { href: '/', label: 'Today' },
    { href: '/timer', label: 'Timer' },
    { href: '/history', label: 'History' },
    { href: '/exercises', label: 'Exercises' },
    { href: '/weekly', label: 'Weekly' },
    { href: '/settings', label: 'Settings' }
  ];

  const isLogin = $derived($page.url.pathname === '/login');

  function isActive(href: string): boolean {
    const path = $page.url.pathname;
    return href === '/' ? path === '/' : path.startsWith(href);
  }

  onMount(async () => {
    const user = await loadUser();
    if (!user && !isLogin) goto('/login');
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
        {#if auth.user}
          <div class="account">
            <span class="muted small">{auth.user.email}</span>
            <button class="logout" onclick={handleLogout}>Sign out</button>
          </div>
        {/if}
      </div>
      <nav>
        {#each nav as item}
          <a href={item.href} class:active={isActive(item.href)}>{item.label}</a>
        {/each}
      </nav>
    </header>
    <main>
      {#if auth.ready && auth.user}
        {@render children()}
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
    font-weight: 700;
    font-size: 1.15rem;
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
    color: var(--muted);
    white-space: nowrap;
    border: 1px solid transparent;
  }
  nav a.active {
    color: var(--text);
    background: var(--surface);
    border-color: var(--border);
  }
</style>
