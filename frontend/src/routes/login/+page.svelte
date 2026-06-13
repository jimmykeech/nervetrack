<script lang="ts">
  import { page } from '$app/stores';

  const errors: Record<string, string> = {
    not_invited: 'That Google account is not on the invite list. Ask the owner to add your email.',
    bad_state: 'Login session expired. Please try again.',
    oauth_failed: 'Google sign-in failed. Please try again.',
    email_unverified: 'Your Google email is not verified.'
  };

  const error = $derived($page.url.searchParams.get('error'));
</script>

<div class="login">
  <div class="card">
    <h1>NerveTrack</h1>
    <p class="muted">Sign in to track your recovery.</p>
    {#if error}
      <p class="error">{errors[error] ?? 'Sign-in failed. Please try again.'}</p>
    {/if}
    <a class="google" href="/api/v1/auth/google/login">
      <span class="g">G</span> Sign in with Google
    </a>
    <p class="muted small">Access is invite-only.</p>
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
    color: var(--red);
    background: rgba(232, 80, 91, 0.12);
    border: 1px solid var(--red);
    border-radius: 8px;
    padding: 0.6rem 0.75rem;
    font-size: 0.9rem;
  }
</style>
