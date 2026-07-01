<script lang="ts">
  import { api } from '$lib/api';
  import {
    blankPainInstanceDraft,
    filledDrafts,
    hasValidDraft,
    type PainInstanceDraft
  } from '$lib/painInstanceForm';
  import { loadPainInstances } from '$lib/stores/painInstances.svelte';

  let drafts = $state<PainInstanceDraft[]>([blankPainInstanceDraft()]);
  let saving = $state(false);
  let error = $state('');

  function addRow() {
    drafts = [...drafts, blankPainInstanceDraft()];
  }

  const canFinish = $derived(hasValidDraft(drafts) && !saving);

  async function done() {
    if (!hasValidDraft(drafts)) return;
    saving = true;
    error = '';
    try {
      for (const d of filledDrafts(drafts)) {
        await api.createPainInstance({
          name: d.name.trim(),
          body_region: d.body_region.trim() || undefined,
          background: d.background.trim() || undefined
        });
      }
      await loadPainInstances();
    } catch (e) {
      error = (e as Error).message;
    } finally {
      saving = false;
    }
  }
</script>

<div class="overlay">
  <div class="modal card">
    <h2 style="margin-top: 0">Tell us about your nerve pain</h2>
    <p class="muted small">
      Add at least one pain issue you're tracking — what it is, roughly where, and any background
      that will help you look back on your recovery. You can add more, or edit these, later from
      Settings.
    </p>
    {#each drafts as draft, i (i)}
      <div class="draft">
        <label
          >Name
          <input bind:value={draft.name} placeholder="e.g. Left sciatic / piriformis" /></label
        >
        <label
          >Body region (optional)
          <input bind:value={draft.body_region} placeholder="e.g. Left glute/hip" /></label
        >
        <label
          >Background (optional)
          <textarea
            bind:value={draft.background}
            placeholder="Onset, cause, anything useful for tracking recovery"
          ></textarea></label
        >
      </div>
    {/each}
    <button type="button" class="link" onclick={addRow}>+ Add another pain issue</button>
    {#if error}<p style="color: var(--bad)">{error}</p>{/if}
    <button class="status-G" style="margin-top: 0.75rem" onclick={done} disabled={!canFinish}>
      {saving ? 'Saving…' : 'Done'}
    </button>
  </div>
</div>

<style>
  .overlay {
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.5);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 100;
    padding: 1rem;
  }
  .modal {
    max-width: 28rem;
    width: 100%;
    max-height: 90vh;
    overflow-y: auto;
  }
  .draft {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
    padding: 0.75rem 0;
    border-bottom: 1px solid var(--border);
  }
  .draft label {
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
    font-size: 0.85rem;
    color: var(--text-muted);
  }
  .link {
    border: none;
    background: none;
    color: var(--text-muted);
    padding: 0;
    font-size: 0.85rem;
    margin-top: 0.25rem;
  }
</style>
