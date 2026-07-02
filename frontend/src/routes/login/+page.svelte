<script lang="ts">
  import { onMount } from 'svelte';
  import { page } from '$app/stores';
  import { goto } from '$app/navigation';
  import { api, type AuthConfig } from '$lib/api';

  const errors: Record<string, string> = {
    not_invited: 'That Google account is not on the invite list. Ask the owner to add your email.',
    bad_state: 'Login session expired. Please try again.',
    oauth_failed: 'Google sign-in failed. Please try again.',
    email_unverified: 'Your Google email is not verified.'
  };
  const urlError = $derived($page.url.searchParams.get('error'));

  let cfg = $state<AuthConfig | null>(null);
  let email = $state('');
  let password = $state('');
  let name = $state('');
  let registering = $state(false);
  let formError = $state('');
  let busy = $state(false);

  onMount(async () => {
    cfg = await api.authConfig();
    if (cfg.mode === 'none') goto('/');
  });

  async function submit(e: Event) {
    e.preventDefault();
    busy = true;
    formError = '';
    try {
      if (registering) await api.register(email, password, name || undefined);
      else await api.login(email, password);
      window.location.href = '/';
    } catch {
      formError = registering
        ? 'Could not register. The email may already be in use.'
        : 'Invalid email or password.';
    } finally {
      busy = false;
    }
  }
</script>

<div class="login">
  <div class="card">
    <h1>NerveTrack</h1>
    <p class="muted">Sign in to track your recovery.</p>
    {#if urlError}
      <p class="error">{errors[urlError] ?? 'Sign-in failed. Please try again.'}</p>
    {/if}

    {#if cfg?.mode === 'google'}
      <a class="google" href="/api/v1/auth/google/login">
        <span class="g">G</span> Sign in with Google
      </a>
      <p class="muted small">Access is invite-only.</p>
    {:else if cfg?.mode === 'password'}
      <form onsubmit={submit}>
        {#if formError}<p class="error">{formError}</p>{/if}
        <input type="email" placeholder="Email" bind:value={email} required />
        <input
          type="password"
          placeholder="Password"
          bind:value={password}
          required
          minlength="8"
        />
        {#if registering}
          <input type="text" placeholder="Name (optional)" bind:value={name} />
        {/if}
        <button type="submit" class="btn-primary" disabled={busy}
          >{registering ? 'Create account' : 'Sign in'}</button
        >
        {#if cfg.allow_registration}
          <button type="button" class="link" onclick={() => (registering = !registering)}>
            {registering ? 'Have an account? Sign in' : 'Create an account'}
          </button>
        {/if}
      </form>
    {:else}
      <p class="muted small">Loading…</p>
    {/if}
  </div>
</div>

<style>
  .login {
    min-height: 80vh;
    display: flex;
    align-items: center;
    justify-content: center;
  }
  .card {
    width: 100%;
    max-width: 22rem;
    text-align: center;
  }
  h1 {
    margin: 0.25rem 0;
  }
  .google {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 0.6rem;
    margin: 1.25rem 0 0.75rem;
    padding: 0.7rem 1rem;
    background: #fff;
    color: #1f1f1f;
    border-radius: 10px;
    font-weight: 600;
  }
  .google:hover {
    background: #f1f3f6;
  }
  .g {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 1.4rem;
    height: 1.4rem;
    border-radius: 50%;
    background: #4285f4;
    color: #fff;
    font-weight: 700;
  }
  .error {
    color: var(--bad);
    background: rgba(232, 80, 91, 0.12);
    border: 1px solid var(--bad);
    border-radius: 8px;
    padding: 0.6rem 0.75rem;
    font-size: 0.9rem;
  }
  form {
    display: flex;
    flex-direction: column;
    gap: 0.6rem;
    margin-top: 1rem;
  }
  input {
    padding: 0.6rem 0.75rem;
    border-radius: 8px;
    border: 1px solid var(--border, #ccc);
    background: var(--surface, #fff);
    color: inherit;
  }
  button[type='submit'] {
    padding: 0.65rem 1rem;
    border-radius: 8px;
    border: none;
    font-weight: 600;
    cursor: pointer;
  }
  button[type='submit']:disabled {
    opacity: 0.6;
  }
  .link {
    background: none;
    border: none;
    color: var(--accent, #4285f4);
    cursor: pointer;
    font-size: 0.9rem;
  }
</style>
