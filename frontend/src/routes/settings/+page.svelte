<script lang="ts">
  import { api } from '$lib/api';
  import { auth, signOut } from '$lib/stores/auth.svelte';
  import { goto } from '$app/navigation';
  import ThemeToggle from '$lib/components/ThemeToggle.svelte';
  import { painInstances, loadPainInstances } from '$lib/stores/painInstances.svelte';
  import { onMount } from 'svelte';

  let file = $state<File | null>(null);

  let newName = $state('');
  let newRegion = $state('');
  let newBackground = $state('');

  onMount(() => {
    if (!painInstances.loaded) loadPainInstances();
  });

  async function addInstance() {
    if (!newName.trim()) return;
    await api.createPainInstance({
      name: newName.trim(),
      body_region: newRegion.trim() || undefined,
      background: newBackground.trim() || undefined
    });
    newName = '';
    newRegion = '';
    newBackground = '';
    await loadPainInstances();
  }

  async function toggleActive(id: string, active: boolean) {
    await api.patchPainInstance(id, { active: !active });
    await loadPainInstances();
  }

  async function handleLogout() {
    await signOut();
    goto('/login');
  }
  let busy = $state(false);
  let result = $state<string>('');
  let error = $state<string>('');

  function onPick(e: Event) {
    const input = e.target as HTMLInputElement;
    file = input.files?.[0] ?? null;
  }

  async function upload() {
    if (!file) return;
    busy = true;
    error = '';
    result = '';
    try {
      const res = await api.importXlsx(file);
      const i = res.imported;
      result = `Imported ${i.daily_entries} daily entries, ${i.sessions} sessions, ${i.weekly_summaries} weekly summaries.`;
    } catch (e) {
      error = (e as Error).message;
    } finally {
      busy = false;
    }
  }
</script>

<div class="card">
  <h2 style="margin-top: 0">Account</h2>
  {#if auth.user}
    <p class="muted small" style="margin-bottom: 0.75rem">
      Signed in as <strong>{auth.user.email}</strong>. Your data is private to this account.
    </p>
  {/if}
  <div class="row" style="align-items: center; gap: 0.6rem; margin-bottom: 0.85rem">
    <span class="small muted">Theme</span>
    <ThemeToggle />
  </div>
  <button onclick={handleLogout}>Sign out</button>
</div>

<div class="card">
  <h2 style="margin-top: 0">Pain instances</h2>
  <p class="muted small">
    The nerve pain issues you're tracking. Tag pain jabs and strengthening sessions with these on
    the Today and Exercises pages.
  </p>
  <ul class="cat">
    {#each painInstances.list as pi (pi.id)}
      <li>
        <span
          >{pi.name}{pi.body_region ? ` · ${pi.body_region}` : ''}{!pi.active
            ? ' (inactive)'
            : ''}</span
        >
        <button class="link" onclick={() => toggleActive(pi.id, pi.active)}
          >{pi.active ? 'retire' : 'reactivate'}</button
        >
      </li>
    {/each}
  </ul>
  <div class="row" style="margin-top: 0.75rem; flex-wrap: wrap; gap: 0.5rem">
    <input bind:value={newName} placeholder="Name, e.g. Left sciatic" style="flex: 1 1 10rem" />
    <input bind:value={newRegion} placeholder="Body region (optional)" style="flex: 1 1 8rem" />
    <button onclick={addInstance}>Add</button>
  </div>
  <textarea
    bind:value={newBackground}
    placeholder="Background (optional)"
    style="margin-top: 0.5rem; width: 100%"
  ></textarea>
</div>

<div class="card">
  <h2 style="margin-top: 0">Import spreadsheet</h2>
  <p class="muted small">
    Upload the existing “Piriformis Recovery Tracker” workbook (.xlsx). The Daily Tracker, Exercise
    Log, and Weekly Summary sheets are imported. Re-running is safe — it matches on date and won't
    duplicate.
  </p>
  <input type="file" accept=".xlsx,.xlsm" onchange={onPick} />
  <div style="margin-top: 0.75rem">
    <button class="status-G" onclick={upload} disabled={!file || busy}>
      {busy ? 'Importing…' : 'Import'}
    </button>
  </div>
  {#if result}<p class="saved" style="margin-top: 0.75rem">{result}</p>{/if}
  {#if error}<p style="color: var(--bad); margin-top: 0.75rem">{error}</p>{/if}
</div>

<div class="card">
  <h3 style="margin-top: 0">About</h3>
  <p class="muted small">
    NerveTrack — Phase 1. Timestamps stored in UTC; dates shown in your local timezone. AI insights
    (weekly summary drafting, free-form Q&amp;A) are planned for Phase 2.
  </p>
</div>

<style>
  .cat {
    list-style: none;
    padding: 0;
    margin: 0;
  }
  .cat li {
    display: flex;
    justify-content: space-between;
    padding: 0.4rem 0;
    border-bottom: 1px solid var(--border);
  }
  .link {
    border: none;
    background: none;
    color: var(--text-muted);
    padding: 0;
    font-size: 0.85rem;
  }
</style>
