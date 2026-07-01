<script lang="ts">
  import { api } from '$lib/api';
  import { auth, signOut } from '$lib/stores/auth.svelte';
  import { goto } from '$app/navigation';
  import ThemeToggle from '$lib/components/ThemeToggle.svelte';
  import { onMount } from 'svelte';
  import type { LlmSettings } from '$lib/types';

  let file = $state<File | null>(null);

  let llm = $state<LlmSettings | null>(null);
  let provider = $state('anthropic');
  let model = $state('');
  let apiKey = $state('');
  let baseUrl = $state('');
  let llmMsg = $state('');
  let llmBusy = $state(false);

  const providers = ['anthropic', 'openai', 'gemini', 'openrouter', 'ollama'];
  const modelHint: Record<string, string> = {
    anthropic: 'anthropic/claude-sonnet-5',
    openai: 'openai/gpt-4.1',
    gemini: 'gemini/gemini-2.5-pro',
    openrouter: 'openrouter/anthropic/claude-sonnet-5',
    ollama: 'ollama/llama3.1'
  };

  onMount(async () => {
    llm = await api.getLlmSettings();
    if (llm.provider) provider = llm.provider;
    model = llm.model ?? '';
    baseUrl = llm.base_url ?? '';
  });

  async function saveLlm() {
    llmBusy = true;
    llmMsg = '';
    try {
      llm = await api.saveLlmSettings({
        provider,
        model: model.trim(),
        api_key: apiKey === '' ? null : apiKey, // blank = keep existing
        base_url: baseUrl.trim() || null
      });
      apiKey = '';
      llmMsg = 'Saved ✓';
    } catch (e) {
      llmMsg = (e as Error).message;
    } finally {
      llmBusy = false;
    }
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
  <h2 style="margin-top: 0">Conditions & records</h2>
  <p class="muted small">
    Manage your conditions, patient background, and documents on the
    <a href="/records">Records</a> page.
  </p>
</div>

<div class="card">
  <h2 style="margin-top: 0">AI model</h2>
  <p class="muted small" style="margin-bottom: 0.75rem">
    Configure a provider and model to enable chat and AI weekly drafts. Your API key is encrypted
    and never leaves this server. For full privacy, run a local model with Ollama — nothing is sent
    externally.
  </p>

  <div class="field">
    <label class="small muted" for="prov">Provider</label>
    <select id="prov" bind:value={provider}>
      {#each providers as p}<option value={p}>{p}</option>{/each}
    </select>
  </div>

  <div class="field">
    <label class="small muted" for="model">Model</label>
    <input id="model" bind:value={model} placeholder={modelHint[provider]} />
  </div>

  <div class="field">
    <label class="small muted" for="key">
      API key {#if llm?.api_key_set}<span>— configured ✓ (leave blank to keep)</span>{/if}
    </label>
    <input
      id="key"
      type="password"
      bind:value={apiKey}
      placeholder={llm?.api_key_set ? '••••••••' : 'Not set'}
    />
  </div>

  {#if provider === 'ollama' || provider === 'openrouter'}
    <div class="field">
      <label class="small muted" for="base">Base URL</label>
      <input
        id="base"
        bind:value={baseUrl}
        placeholder={provider === 'ollama'
          ? 'http://localhost:11434'
          : 'https://openrouter.ai/api/v1'}
      />
    </div>
  {/if}

  <div class="row" style="margin-top: 0.75rem; gap: 0.6rem; align-items: center">
    <button onclick={saveLlm} disabled={llmBusy || !model.trim()}>Save AI settings</button>
    {#if llmMsg}<span class="small muted">{llmMsg}</span>{/if}
  </div>
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
    NerveTrack. Timestamps stored in UTC; dates shown in your local timezone. AI insights (weekly
    summary drafting, free-form Q&amp;A over your data) are available — configure a model above,
    then use the Chat page and the Weekly “Draft with AI” button.
  </p>
</div>
