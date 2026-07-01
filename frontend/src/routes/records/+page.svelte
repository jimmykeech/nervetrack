<script lang="ts">
  import { onMount } from 'svelte';
  import { api } from '$lib/api';
  import { RecordsStore } from '$lib/stores/records.svelte';

  const records = new RecordsStore();
  let expanded = $state<string | null>(null);
  let noteDraft = $state<Record<string, string>>({});
  let profileMsg = $state('');

  onMount(() => records.load());

  async function saveProfile(e: Event) {
    e.preventDefault();
    if (!records.profile) return;
    await records.saveProfile(records.profile);
    profileMsg = 'Saved ✓';
  }

  async function toggle(id: string) {
    if (expanded === id) {
      expanded = null;
      return;
    }
    expanded = id;
    if (!records.details[id]) await records.openCondition(id);
  }

  async function saveDetails(id: string) {
    const d = records.details[id];
    if (!d) return;
    await api.patchPainInstance(id, {
      body_region: d.instance.body_region,
      background: d.instance.background
    });
  }

  async function addNote(id: string) {
    const body = (noteDraft[id] ?? '').trim();
    if (!body) return;
    await records.addNote(id, body);
    noteDraft = { ...noteDraft, [id]: '' };
  }

  async function upload(e: Event, ownerType: string, instanceId?: string) {
    const input = e.target as HTMLInputElement;
    const file = input.files?.[0];
    if (!file) return;
    const title = prompt('Document title', file.name) ?? file.name;
    const summary = prompt('Notes/summary for the AI (optional)') ?? '';
    const form = new FormData();
    form.append('file', file);
    form.append('title', title);
    form.append('owner_type', ownerType);
    if (summary) form.append('notes', summary);
    if (instanceId) form.append('instance_id', instanceId);
    await records.uploadDoc(form, ownerType, instanceId);
    input.value = '';
  }
</script>

<div class="card">
  <h2 style="margin-top: 0">Patient background</h2>
  {#if records.profile}
    <form class="grid" onsubmit={saveProfile}>
      <label>Date of birth <input type="date" bind:value={records.profile.dob} /></label>
      <label>Sex <input bind:value={records.profile.sex} placeholder="e.g. male" /></label>
      <label
        >Height (cm) <input
          type="number"
          step="0.1"
          bind:value={records.profile.height_cm}
        /></label
      >
      <label
        >Weight (kg) <input
          type="number"
          step="0.1"
          bind:value={records.profile.weight_kg}
        /></label
      >
      <label class="wide"
        >Lifestyle
        <textarea
          bind:value={records.profile.lifestyle}
          rows="3"
          placeholder="Activity, work setup, sleep, habits…"
        ></textarea>
      </label>
      <label class="wide"
        >Medical history
        <textarea
          bind:value={records.profile.medical_history}
          rows="4"
          placeholder="Previous events/conditions, surgeries, medications…"
        ></textarea>
      </label>
      <div class="wide">
        <button type="submit">Save background</button>
        {#if profileMsg}<span class="small muted" style="margin-left: 0.6rem">{profileMsg}</span
          >{/if}
      </div>
    </form>
  {/if}
</div>

<div class="card">
  <h2 style="margin-top: 0">Conditions</h2>
  {#each records.conditions as c (c.id)}
    <div class="condition">
      <button class="crow" onclick={() => toggle(c.id)}>
        <strong>{c.name}</strong>
        {#if c.body_region}<span class="muted small">{c.body_region}</span>{/if}
        <span class="chev">{expanded === c.id ? '▾' : '▸'}</span>
      </button>
      {#if expanded === c.id && records.details[c.id]}
        {@const d = records.details[c.id]}
        <div class="cbody">
          <label
            >Body region
            <input bind:value={d.instance.body_region} /></label
          >
          <label
            >Details
            <textarea
              bind:value={d.instance.background}
              rows="4"
              placeholder="Nature of the condition, diagnosis, current status…"
            ></textarea>
          </label>
          <button onclick={() => saveDetails(c.id)}>Save details</button>

          <h4>Notes</h4>
          <div class="row">
            <input placeholder="Add a dated note…" bind:value={noteDraft[c.id]} />
            <button onclick={() => addNote(c.id)}>Add</button>
          </div>
          <ul class="log">
            {#each d.notes as n (n.id)}
              <li>
                <span class="muted small">{n.occurred_at.slice(0, 10)}</span>
                {n.body}
                <button class="link" onclick={() => records.deleteNote(c.id, n.id)}>delete</button>
              </li>
            {/each}
          </ul>

          <h4>Documents</h4>
          <ul class="log">
            {#each d.documents as doc (doc.id)}
              <li>
                <a href={api.documentDownloadUrl(doc.id)} target="_blank" rel="noreferrer"
                  >{doc.title}</a
                >
                {#if doc.notes}<span class="muted small">— {doc.notes}</span>{/if}
                <button class="link" onclick={() => records.deleteDoc(doc.id, c.id)}>delete</button>
              </li>
            {/each}
          </ul>
          <input type="file" onchange={(e) => upload(e, 'condition', c.id)} />
        </div>
      {/if}
    </div>
  {/each}
  {#if records.conditions.length === 0}
    <p class="muted small">No conditions yet — add one from the onboarding prompt.</p>
  {/if}
</div>

<div class="card">
  <h2 style="margin-top: 0">General documents</h2>
  <p class="muted small">Reports/imaging not tied to a single condition.</p>
  <ul class="log">
    {#each records.generalDocs as doc (doc.id)}
      <li>
        <a href={api.documentDownloadUrl(doc.id)} target="_blank" rel="noreferrer">{doc.title}</a>
        {#if doc.notes}<span class="muted small">— {doc.notes}</span>{/if}
        <button class="link" onclick={() => records.deleteDoc(doc.id)}>delete</button>
      </li>
    {/each}
  </ul>
  <input type="file" onchange={(e) => upload(e, 'profile')} />
</div>

<style>
  .grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 0.75rem;
  }
  .grid label {
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
  }
  .grid .wide {
    grid-column: 1 / -1;
  }
  .condition {
    border-bottom: 1px solid var(--border);
    padding: 0.4rem 0;
  }
  .crow {
    display: flex;
    align-items: center;
    gap: 0.6rem;
    width: 100%;
    background: none;
    border: none;
    cursor: pointer;
    text-align: left;
    color: inherit;
    padding: 0.35rem 0;
  }
  .chev {
    margin-left: auto;
  }
  .cbody {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
    padding: 0.5rem 0 0.75rem;
  }
  .cbody label {
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
  }
  .log {
    list-style: none;
    padding: 0;
    margin: 0.25rem 0;
  }
  .log li {
    padding: 0.3rem 0;
    border-bottom: 1px solid var(--border);
  }
  .link {
    border: none;
    background: none;
    color: var(--text-muted);
    padding: 0 0 0 0.5rem;
    font-size: 0.8rem;
    cursor: pointer;
  }
  @media (max-width: 640px) {
    .grid {
      grid-template-columns: 1fr;
    }
  }
</style>
